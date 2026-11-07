"""Tool registry with permission-gated execution.

Every call is permission-checked against the calling agent's level and
appended to the activity_logs audit table. Calls that need a higher level
create an approval request and raise WaitingForApproval.

SOLE-ADMIN / SELF-MODIFICATION GUARDRAIL: any tool call that would write
outside the project workspaces (DATA_DIR/projects/), touch the auth/role/
permission tables (users, tool_permissions, approvals), or modify the
arthur-ai source tree, config, or secrets is classified LEVEL 3. No agent
(max level 2) can ever reach level 3, so such calls ALWAYS create an
approval for the owner and never execute autonomously — there is no
auto-approve path. The file/shell jails remain as defense-in-depth.
"""
from __future__ import annotations

import json
import os
import re

from backend.database.db import DATA_DIR, get_conn, now

# Projects workspace: the ONLY tree agents may write to without a
# level-3 self-modification approval.
_PROJECTS_ROOT = os.path.realpath(os.path.join(DATA_DIR, "projects"))

# Heuristic patterns for code/shell that touches ARTHUR's own identity:
# auth/role/permission tables, role-management helpers, the source tree,
# or secrets. Conservative by design (may over-trip -> owner approves/denies).
_SELF_MOD_PATTERNS = [
    re.compile(
        r"(?i)\b(update|delete\s+from|insert\s+into|drop\s+table)\b"
        r".{0,60}\b(users|tool_permissions|push_tokens)\b"
    ),
    re.compile(
        r"\b(create_user|update_user_role|set_tool_permission|require_admin|"
        r"is_admin|resolve_approval|create_approval)\b"
    ),
    re.compile(r"arthur-ai/(backend|mobile)/|backend/(database|security|tools|agents|api)/"),
    re.compile(r"(?i)\.env\b|secrets?/|ARTHUR_LLM_API_KEY|ARTHUR_OWNER"),
]


def _self_modification_level(name, kwargs):
    """Return 3 when the call touches ARTHUR itself; else 0.

    - write_file/edit_file: level 3 unless the resolved path stays inside
      DATA_DIR/projects/ (the agent project workspace).
    - run_shell/run_python: level 3 when the command/code matches the
      self-modification patterns (auth tables, role helpers, source tree,
      secrets).
    """
    if name in ("write_file", "edit_file"):
        p = str(kwargs.get("path", "") or "")
        abs_p = p if os.path.isabs(p) else os.path.join(DATA_DIR, p)
        try:
            resolved = os.path.realpath(abs_p)
        except Exception:
            return 3
        try:
            common = os.path.commonpath([resolved, _PROJECTS_ROOT])
        except ValueError:
            return 3
        return 0 if common == _PROJECTS_ROOT else 3
    if name in ("run_shell", "run_python"):
        blob = str(kwargs.get("cmd", kwargs.get("code", "")) or "")
        if any(pat.search(blob) for pat in _SELF_MOD_PATTERNS):
            return 3
        return 0
    return 0


class WaitingForApproval(Exception):
    """Raised when a tool call requires an approval first.

    Carries the created approval's id in ``approval_id`` so the worker can
    park the task in WAITING_FOR_APPROVAL.
    """

    def __init__(self, approval_id=None):
        self.approval_id = approval_id
        super().__init__(
            "tool call requires approval (approval_id=%s)" % (approval_id,)
        )


class ToolRegistry:
    """Registry of named tool functions with permission levels."""

    def __init__(self):
        self._tools = {}

    def register(self, name, fn, permission_level, description=""):
        """Register ``fn`` under ``name`` requiring ``permission_level``."""
        self._tools[name] = {
            "fn": fn,
            "permission_level": permission_level,
            "description": description,
        }

    def get(self, name):
        """Return the tool entry for ``name`` (or None)."""
        return self._tools.get(name)

    def names(self):
        return list(self._tools)

    def call(self, agent, name, **kwargs):
        """Call tool ``name`` on behalf of ``agent``.

        ``agent`` must expose ``.name`` and ``.permission_level``.
        Raises WaitingForApproval (after creating the approval row) when the
        agent's level is below the tool's level. On tool exception, logs
        ok=0 and re-raises.
        """
        from backend.security import approvals  # lazy: avoid any import cycle
        from backend.security.secrets import scrub_dict  # lazy

        if name not in self._tools:
            raise KeyError("unknown tool: %s" % (name,))
        tool = self._tools[name]
        required_level = max(
            tool["permission_level"], _self_modification_level(name, kwargs)
        )
        if agent.permission_level < required_level:
            approval_id = approvals.create_approval(
                kind="tool_permission",
                subject="%s -> %s" % (agent.name, name),
                detail={
                    "agent": agent.name,
                    "tool": name,
                    # Scrubbed: approval detail is shown on dashboards.
                    "args": scrub_dict(kwargs),
                    "level_required": required_level,
                    "guardrail": (
                        "self-modification" if required_level == 3
                        and tool["permission_level"] < 3 else None
                    ),
                },
                requested_by=agent.name,
            )
            raise WaitingForApproval(approval_id)
        try:
            result = tool["fn"](**kwargs)
        except Exception as exc:
            self._log(agent.name, name, kwargs, ok=False, error=str(exc))
            raise
        self._log(agent.name, name, kwargs, ok=True, error=None)
        return result

    def _log(self, agent_name, tool_name, args, ok, error):
        # Secrets must NEVER reach the audit log: redact key-like values in
        # both the args payload and the error text before persisting.
        from backend.security.secrets import scrub, scrub_dict  # lazy

        safe_args = (
            scrub_dict(args) if isinstance(args, dict) else scrub(args)
        )
        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO activity_logs (ts, agent, tool, args, ok, error)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (now(), agent_name, tool_name, scrub(json.dumps(safe_args)),
                 1 if ok else 0, scrub(error)),
            )
            conn.commit()
        finally:
            conn.close()


def make_registry():
    """Build a registry with all built-in tools registered."""
    from backend.tools import web, files, terminal, python_tool

    reg = ToolRegistry()
    reg.register("web_search", web.web_search, 0,
                 "Search the web (DuckDuckGo).")
    reg.register("fetch_url", web.fetch_url, 0,
                 "Fetch a URL and return its text (first 4000 chars).")
    reg.register("read_file", files.read_file, 0,
                 "Read a file inside the DATA_DIR jail.")
    reg.register("list_files", files.list_files, 0,
                 "List files inside the DATA_DIR jail.")
    reg.register("write_file", files.write_file, 1,
                 "Write a file inside the DATA_DIR jail.")
    reg.register("edit_file", files.edit_file, 1,
                 "Replace text in a file inside the DATA_DIR jail.")
    reg.register("run_shell", terminal.run_shell, 1,
                 "Run a shell command (guarded, jailed under ARTHUR_HOME).")
    reg.register("run_python", python_tool.run_python, 1,
                 "Run Python code via sys.executable.")
    return reg
