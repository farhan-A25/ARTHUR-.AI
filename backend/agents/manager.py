"""Manager agent (backend/agents/manager.py) — Builder D.

Owns the goal lifecycle: intake -> planning -> supervision (monitor_tick) ->
completion verification -> final report. Permission level 2.

PERMISSION RULE (contract): never assign a step whose tool level exceeds the
agent's level. In particular the level-0 researcher gets read-only steps only.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import json
import re
import time

from backend.database.db import init_db, get_conn, now, DATA_DIR
from backend.memory.store import update_project_profile
from backend.security.approvals import create_approval, list_approvals
from backend.tasks import queue as q

DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"
TERMINAL_STATES = ("COMPLETED", "FAILED")

# ---------------------------------------------------------------------------
# NOTES_CLI demo templates (byte-correct, working)
# ---------------------------------------------------------------------------

NOTES_SLUG = "tiny-markdown-notes-cli"
NOTES_DIR = "projects/" + NOTES_SLUG  # relative to DATA_DIR (files.py jail root)

RESEARCH_MD = '''# Notes CLI — research notes
Design: single-file Python CLI using argparse with subcommands `add <text>` and `list`.
Storage: append-only Markdown file (notes.md), one `- <text>` bullet per line.
Conventions: `--file` flag overrides the storage path; exit code 0 on success.
Test plan: add a note, list notes, assert the note appears in the output.
'''

NOTES_PY = '''#!/usr/bin/env python3
"""Tiny markdown notes CLI (ARTHUR demo)."""
import argparse
import os
import sys

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.md")

def add_note(text, path):
    with open(path, "a", encoding="utf-8") as f:
        f.write("- " + text + "\\n")

def list_notes(path):
    if not os.path.exists(path):
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:])
    return items

def main(argv=None):
    p = argparse.ArgumentParser(description="Tiny markdown notes CLI")
    p.add_argument("--file", default=DEFAULT_FILE, help="notes file")
    sub = p.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("add", help="add a note")
    pa.add_argument("text", help="note text")
    sub.add_parser("list", help="list notes")
    a = p.parse_args(argv)
    if a.cmd == "add":
        add_note(a.text, a.file)
        print("added")
    elif a.cmd == "list":
        for n in list_notes(a.file):
            print(n)

if __name__ == "__main__":
    main()
'''

TEST_SMOKE_PY = '''import os
import subprocess
import sys

d = os.path.dirname(os.path.abspath(__file__))
f = os.path.join(d, "notes.md")
if os.path.exists(f):
    os.remove(f)
r = subprocess.run([sys.executable, "notes.py", "add", "hello arthur"], cwd=d, capture_output=True, text=True)
assert r.returncode == 0, r.stderr
r = subprocess.run([sys.executable, "notes.py", "list"], cwd=d, capture_output=True, text=True)
assert r.returncode == 0 and "hello arthur" in r.stdout, r.stdout + r.stderr
print("SMOKE OK")
'''

README_MD = '''# Tiny Markdown Notes CLI

A tiny CLI that stores notes as Markdown bullets (one `- <text>` line per note).

## Usage

```sh
python notes.py add "buy milk"
python notes.py list
```

Use `--file PATH` to choose a different notes file.
'''


class ManagerAgent:
    name = "manager"
    permission_level = 2

    def __init__(self, registry, llm):
        self.registry = registry
        self.llm = llm

    # ------------------------------------------------------------------
    # Goal lifecycle
    # ------------------------------------------------------------------

    def handle_goal(self, goal_text, wait=True, timeout=600):
        """Run the full goal lifecycle; return the final report string."""
        init_db()

        plan = self.plan_goal(goal_text)
        slug = plan.get("project_slug") or self._slugify(goal_text)

        project_id = q.create_project(slug, description=goal_text)
        update_project_profile(project_id, {"goal": goal_text})
        self._store_completion_conditions(project_id, plan["completion_conditions"])

        # Create tasks QUEUED, resolving 1-based dep indices -> task ids.
        created_ids = []
        for spec in plan["tasks"]:
            dep_ids = []
            for d in spec.get("deps") or []:
                if isinstance(d, int) and 1 <= d <= len(created_ids):
                    dep_ids.append(created_ids[d - 1])
            tid = q.create_task(
                project_id,
                spec["title"],
                spec["agent"],
                deps=dep_ids,
                success_criteria=spec.get("success_criteria", ""),
                steps=spec.get("steps"),
                max_attempts=spec.get("max_attempts", 3),
            )
            q.set_state(tid, "QUEUED")
            created_ids.append(tid)

        summary = self._plan_summary(goal_text, slug, plan, created_ids)
        self._log_message(project_id, summary)
        print(summary, flush=True)

        if wait:
            deadline = time.time() + timeout
            while time.time() < deadline:
                tasks = q.list_tasks(project_id)
                if tasks and all(t["state"] in TERMINAL_STATES for t in tasks):
                    break
                self.monitor_tick()
                time.sleep(1)

        ok, unmet = self.verify_completion_conditions(project_id)
        return self._final_report(goal_text, slug, project_id, ok, unmet)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan_goal(self, goal):
        """Return {"project_slug", "completion_conditions", "tasks"}.

        In DEMO_MODE this is template-driven (deterministic, no LLM key).
        Task deps are 1-based indices into the tasks list (resolved to ids by
        handle_goal).
        """
        if DEMO_MODE:
            if "notes" in goal.lower():
                return self._notes_cli_plan()
            # "resume" and everything else: generic scaffold plan
            return self._generic_plan(goal, self._slugify(goal))
        return self._llm_plan(goal)

    def _notes_cli_plan(self):
        d = NOTES_DIR
        return {
            "project_slug": NOTES_SLUG,
            "completion_conditions": [
                "research.md exists",
                "notes.py exists",
                "add/list commands work via smoke test",
                "README.md exists",
                "all tasks completed",
            ],
            "tasks": [
                {
                    "title": "Research notes CLI design",
                    "agent": "researcher",
                    "deps": [],
                    "success_criteria": "research summary in output",
                    # Level-0 agent: read-only tools only (no write/edit/shell).
                    "steps": [
                        {
                            "tool": "web_search",
                            "args": {"query": "tiny markdown notes CLI design best practices"},
                        }
                    ],
                },
                {
                    "title": "Implement notes CLI",
                    "agent": "developer",
                    "deps": [1],
                    "success_criteria": "notes.py compiles",
                    "steps": [
                        {"tool": "write_file",
                         "args": {"path": d + "/research.md", "content": RESEARCH_MD}},
                        {"tool": "write_file",
                         "args": {"path": d + "/notes.py", "content": NOTES_PY}},
                        {"tool": "write_file",
                         "args": {"path": d + "/README.md", "content": README_MD}},
                        {"tool": "run_shell",
                         "args": {"cmd": "python3 -m py_compile notes.py", "cwd": d}},
                    ],
                },
                {
                    "title": "Smoke test notes CLI",
                    "agent": "qa",
                    "deps": [2],
                    "success_criteria": "SMOKE OK",
                    "steps": [
                        {"tool": "write_file",
                         "args": {"path": d + "/test_smoke.py", "content": TEST_SMOKE_PY}},
                        {"tool": "run_shell",
                         "args": {"cmd": "python3 test_smoke.py", "cwd": d}},
                    ],
                },
            ],
        }

    def _generic_plan(self, goal, slug):
        proj = "projects/" + slug
        short = goal[:60]
        return {
            "project_slug": slug,
            "completion_conditions": ["all tasks completed"],
            "tasks": [
                {
                    "title": "Research: " + short,
                    "agent": "researcher",
                    "deps": [],
                    "success_criteria": "research summary in output",
                    "steps": [
                        {"tool": "web_search", "args": {"query": goal[:120]}},
                    ],
                },
                {
                    "title": "Build: " + short,
                    "agent": "developer",
                    "deps": [1],
                    "success_criteria": "scaffold written",
                    "steps": [
                        {"tool": "write_file",
                         "args": {"path": proj + "/plan.md",
                                  "content": "# Plan\n\nGoal: %s\n" % goal}},
                    ],
                },
                {
                    "title": "Verify scaffold",
                    "agent": "qa",
                    "deps": [2],
                    "success_criteria": "files present",
                    "steps": [
                        {"tool": "list_files", "args": {"path": proj}},
                    ],
                },
            ],
        }

    def _llm_plan(self, goal):
        system = (
            "You are ARTHUR's planner. Return ONLY a JSON object with keys "
            '"completion_conditions" (list of strings) and "tasks" (list of '
            '{"title","agent","deps","success_criteria","steps"} where deps are '
            "1-based indices and steps are {\"tool\",\"args\"} objects). "
            "Agents: researcher (level 0: web_search, fetch_url, read_file, "
            "list_files only), developer (level 1), qa (level 1), "
            "analyst (level 1), browser (level 1). Never give an agent a step "
            "whose tool level exceeds the agent's level."
        )
        try:
            raw = self.llm.chat(
                [{"role": "user", "content": "Plan this goal as tasks: " + goal}],
                system=system,
            )
            data = json.loads(raw)
            tasks = data.get("tasks") or []
            if not tasks:
                raise ValueError("LLM returned no tasks")
            return {
                "project_slug": self._slugify(goal),
                "completion_conditions": data.get("completion_conditions")
                or ["all tasks completed"],
                "tasks": tasks,
            }
        except Exception:
            return self._generic_plan(goal, self._slugify(goal))

    # ------------------------------------------------------------------
    # Supervision
    # ------------------------------------------------------------------

    def monitor_tick(self):
        """Supervise FAILED tasks.

        First two failures -> requeue with a fix note; third -> escalate to a
        human approval (kind="task_failed"). Returns counts incl. pending
        approvals.
        """
        counts = {"requeued": 0, "escalated": 0, "pending_approvals": 0}
        for task in q.list_tasks(state="FAILED"):
            fix_notes = (task.get("checkpoint") or {}).get("fix_notes") or []
            if len(fix_notes) < 2:
                analysis = (task.get("error") or "")[:200]
                note = "manager analysis: %s" % (analysis or "no error captured")
                q.requeue_with_fix(task["id"], note)
                counts["requeued"] += 1
            else:
                if not self._already_escalated(task["id"]):
                    create_approval(
                        kind="task_failed",
                        subject="task failed repeatedly: %s" % task["title"],
                        detail={"task_id": task["id"],
                                "project_id": task["project_id"],
                                "error": task.get("error")},
                        requested_by="manager",
                    )
                    counts["escalated"] += 1
        counts["pending_approvals"] = len(list_approvals(state="pending"))
        if counts["requeued"] or counts["escalated"]:
            print("[manager] monitor_tick: requeued=%d escalated=%d pending_approvals=%d"
                  % (counts["requeued"], counts["escalated"],
                     counts["pending_approvals"]), flush=True)
        return counts

    @staticmethod
    def _already_escalated(task_id):
        """True if a pending task_failed approval already exists for task_id.

        Prevents monitor_tick from filing a duplicate approval on every poll
        while a repeatedly-failed task awaits human review.
        """
        for approval in list_approvals(state="pending"):
            if approval.get("kind") != "task_failed":
                continue
            try:
                detail = json.loads(approval.get("detail") or "{}")
            except (TypeError, ValueError):
                continue
            if detail.get("task_id") == task_id:
                return True
        return False

    # ------------------------------------------------------------------
    # Verification + reporting
    # ------------------------------------------------------------------

    def verify_completion_conditions(self, project_id):
        """Check each completion condition; return (ok, unmet_list).

        File-existence conditions are checked under
        DATA_DIR/projects/<slug>/; "add/list" is satisfied by a COMPLETED qa
        task; "all tasks completed" requires every task COMPLETED.
        """
        project = self._get_project(project_id)
        slug = project["name"]
        conditions = project.get("completion_conditions") or []
        tasks = q.list_tasks(project_id)
        base = os.path.join(DATA_DIR, "projects", slug)

        unmet = []
        for cond in conditions:
            if not self._condition_met(cond, tasks, base):
                unmet.append(cond)
        return (len(unmet) == 0, unmet)

    def _condition_met(self, cond, tasks, base):
        cl = cond.lower()
        if "all tasks completed" in cl:
            return bool(tasks) and all(t["state"] == "COMPLETED" for t in tasks)
        if "add/list" in cl:
            return any(t["agent"] == "qa" and t["state"] == "COMPLETED"
                       for t in tasks)
        if "exists" in cl:
            m = re.search(r"([\w.\-]+\.(?:py|md|txt|json))", cond)
            return bool(m) and os.path.exists(os.path.join(base, m.group(1)))
        # Unknown condition: fall back to all-tasks-COMPLETED.
        return bool(tasks) and all(t["state"] == "COMPLETED" for t in tasks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(text):
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug[:60] or "goal"

    @staticmethod
    def _store_completion_conditions(project_id, conditions):
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE projects SET completion_conditions = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(list(conditions or [])), now(), project_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _get_project(project_id):
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if row is None:
                raise KeyError("project %r not found" % (project_id,))
            d = dict(row)
            d["completion_conditions"] = json.loads(
                d.get("completion_conditions") or "[]")
            return d
        finally:
            conn.close()

    @staticmethod
    def _log_message(project_id, content):
        # Secrets must never reach chat history: scrub key-like values.
        from backend.security.secrets import scrub

        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO messages (project_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (project_id, "manager", scrub(content), now()),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _plan_summary(goal_text, slug, plan, task_ids):
        lines = ["[manager] plan for goal: %s" % goal_text,
                 "[manager] project: %s (%d tasks)" % (slug, len(task_ids))]
        for i, (spec, tid) in enumerate(zip(plan["tasks"], task_ids), 1):
            lines.append("  %d. [%s] %s (task %d, deps %s)" % (
                i, spec["agent"], spec["title"], tid, spec.get("deps") or []))
        return "\n".join(lines)

    def _final_report(self, goal_text, slug, project_id, ok, unmet):
        tasks = q.list_tasks(project_id)
        project = self._get_project(project_id)
        conditions = project.get("completion_conditions") or []
        unmet_set = set(unmet)

        lines = []
        lines.append("=" * 60)
        lines.append("ARTHUR — GOAL REPORT")
        lines.append("=" * 60)
        lines.append("Goal: %s" % goal_text)
        lines.append("")
        lines.append("Plan (%d tasks):" % len(tasks))
        for i, t in enumerate(tasks, 1):
            lines.append("  %d. %s: %s (attempts %d)"
                         % (i, t["title"], t["state"], t["attempts"]))
        lines.append("")
        lines.append("Completion checklist:")
        for cond in conditions:
            mark = "x" if cond not in unmet_set else " "
            lines.append("[%s] %s" % (mark, cond))
        lines.append("")
        lines.append("Project dir: %s" % os.path.join(DATA_DIR, "projects", slug))
        lines.append("Result: %s" % ("ALL CONDITIONS MET" if ok else "INCOMPLETE"))
        lines.append("ARTHUR MVP demo complete.")
        return "\n".join(lines)
