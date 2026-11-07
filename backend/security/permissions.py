"""Permission levels and role checks for ARTHUR.

Levels 0..3 gate tool access; roles (Owner/Admin) gate administrative
actions such as resolving approvals and managing users.

SOLE-ADMIN GUARANTEE (highest priority):
- The owner account is the one and only admin. No built-in, default,
  backdoor, "system", "assistant", or agent admin accounts exist, and no
  code path may create one.
- Only the existing admin can grant/revoke roles; no self-promotion path
  exists for agents or non-admin users (see backend/database/db.py).
- Admin privilege NEVER bypasses the audit log or the approval queue: a
  level-3 tool action requested by any agent (including the manager) still
  creates an approval request and is logged in activity_logs. The admin's
  power is to *resolve* that approval, not to skip it. Non-admin users
  cannot resolve approvals or manage users.
- Agents (including the Manager) cannot modify ARTHUR's own codebase,
  configuration, permissions, roles, or user accounts autonomously: the
  ToolRegistry classifies such operations as LEVEL 3, which always
  requires explicit owner approval with no auto-approve path.
"""

import json

from backend.database.db import get_conn, get_user_by_name, now

LEVELS = {
    0: {
        "name": "READ",
        "description": (
            "Read-only access: web_search, fetch_url, read_file, list_files. "
            "No writes, no code execution, no external actions."
        ),
    },
    1: {
        "name": "LOW RISK",
        "description": (
            "Local low-risk actions: write_file, edit_file (jailed to DATA_DIR), "
            "run_shell (guarded, jailed under ARTHUR_HOME), run_python."
        ),
    },
    2: {
        "name": "EXTERNAL ACTIONS",
        "description": (
            "External actions: sending messages or email, posting to external "
            "services, modifying external state. Reserved for manager-level agents."
        ),
    },
    3: {
        "name": "HIGH RISK",
        "description": (
            "High-risk operations: broad destructive writes, unguarded execution, "
            "sensitive data access. Always gated by an approval request and "
            "fully audited; admin approval resolves but never skips the queue."
        ),
    },
}


def can(agent_level, tool_level):
    """True if an agent at ``agent_level`` may use a tool at ``tool_level``."""
    return agent_level >= tool_level


def describe(level):
    """Human-readable description of a permission level."""
    entry = LEVELS.get(level)
    if entry is None:
        return "level %s (unknown)" % (level,)
    return "level %s (%s): %s" % (level, entry["name"], entry["description"])


def is_admin(user):
    """True if the user dict has admin privileges. Owner/Admin only."""
    return bool(user.get("is_admin")) if isinstance(user, dict) else False


def can_resolve_approvals(user):
    """Only admins (Owner/Admin) may resolve approvals."""
    return is_admin(user)


def can_manage_users(user):
    """Only admins (Owner/Admin) may manage users."""
    return is_admin(user)


def require_admin_user(name):
    """Return the user dict for ``name`` if it is the admin.

    Raises PermissionError when the user does not exist or is not an
    admin. Central choke point for every admin-gated action.
    """
    user = get_user_by_name(name)
    if user is None or not is_admin(user):
        raise PermissionError(
            "user %r is not an admin and cannot perform this action" % (name,)
        )
    return user


def set_tool_permission(agent_name, tool_name, allowed, actor_name):
    """Grant/revoke a tool permission row. Admin-actor only; audited.

    Every permission change appends an activity_logs row with the actor,
    timestamp, and old->new diff. Non-admin actors get PermissionError.
    """
    actor = require_admin_user(actor_name)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM tool_permissions WHERE agent_name = ? AND tool_name = ?",
            (agent_name, tool_name),
        ).fetchone()
        old = dict(row) if row else None
        if old is None:
            conn.execute(
                "INSERT INTO tool_permissions (agent_name, tool_name, allowed)"
                " VALUES (?, ?, ?)",
                (agent_name, tool_name, 1 if allowed else 0),
            )
        else:
            conn.execute(
                "UPDATE tool_permissions SET allowed = ?"
                " WHERE agent_name = ? AND tool_name = ?",
                (1 if allowed else 0, agent_name, tool_name),
            )
        conn.execute(
            "INSERT INTO activity_logs (ts, agent, tool, args, ok, error)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                now(),
                actor["name"],
                "permission_change",
                json.dumps(
                    {
                        "agent_name": agent_name,
                        "tool_name": tool_name,
                        "old_allowed": (bool(old["allowed"]) if old else None),
                        "new_allowed": bool(allowed),
                    }
                ),
                1,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()
