"""ARTHUR user data rights: export (JSON dump) and full account deletion.

- ``export_user_data(name)`` returns a dict with everything ARTHUR stores
  about the user: profile, team memberships, session metadata, activity
  log entries where they were the actor, and approvals they requested or
  resolved. ``password_hash`` is NEVER included in an export.
- ``delete_user_account(name, actor_name)`` cascade-deletes the account:
  sessions, login attempts, team memberships, push tokens, their activity
  log entries, their pending approvals, then the user row itself.
  The actor must be the admin or the account owner themselves.
  The SOLE ADMIN can never be deleted (sole-admin guarantee).

Both are exposed via the API (``GET /api/user/export``,
``DELETE /api/user``) and the CLI (``/export``, ``/delete-account``).
"""
from __future__ import annotations

from backend.database.db import get_conn, get_user_by_name, now
from backend.security.secrets import scrub_dict


def export_user_data(name: str) -> dict:
    """JSON-serializable dump of all data ARTHUR holds about ``name``."""
    user = get_user_by_name(name)
    if user is None:
        raise KeyError("user %r not found" % (name,))
    conn = get_conn()
    try:
        teams = [
            dict(r)
            for r in conn.execute(
                "SELECT t.id, t.name, tm.role AS membership_role, t.created_at"
                " FROM team_members tm JOIN teams t ON t.id = tm.team_id"
                " WHERE tm.user_id = ?",
                (user["id"],),
            ).fetchall()
        ]
        sessions = [
            dict(r)
            for r in conn.execute(
                "SELECT id, created_at, expires_at, revoked FROM sessions"
                " WHERE user_id = ? ORDER BY id",
                (user["id"],),
            ).fetchall()
        ]
        activity = [
            dict(r)
            for r in conn.execute(
                "SELECT id, ts, tool, args, ok, error FROM activity_logs"
                " WHERE agent = ? ORDER BY id",
                (user["name"],),
            ).fetchall()
        ]
        approvals = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM approvals WHERE requested_by = ?"
                " OR resolved_by = ? ORDER BY id",
                (user["name"], user["name"]),
            ).fetchall()
        ]
        push = [
            dict(r)
            for r in conn.execute(
                "SELECT id, platform, created_at FROM push_tokens ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()
    profile = {k: v for k, v in user.items() if k != "password_hash"}
    return scrub_dict(
        {
            "exported_at": now(),
            "profile": profile,
            "teams": teams,
            "sessions": sessions,
            "activity_logs": activity,
            "approvals": approvals,
            "push_tokens": push,
            "note": "push_tokens lists this account's registered devices"
            " (metadata only — raw token values are never exported).",
        }
    )


def delete_user_account(name: str, actor_name: str) -> dict:
    """Cascade-delete ``name``'s account. Returns a summary of deleted rows.

    Raises PermissionError when the actor is neither the admin nor the
    account owner, and always refuses to delete the sole admin.
    """
    from backend.security.permissions import is_admin

    target = get_user_by_name(name)
    if target is None:
        raise KeyError("user %r not found" % (name,))
    actor = get_user_by_name(actor_name)
    if actor is None or not (
        is_admin(actor) or actor["name"] == target["name"]
    ):
        raise PermissionError(
            "only the account owner or an admin may delete an account"
        )
    if target["is_admin"]:
        raise PermissionError(
            "sole-admin guarantee: the owner/admin account cannot be deleted"
        )
    conn = get_conn()
    try:
        counts = {}
        for table, where, params in [
            ("sessions", "user_id = ?", (target["id"],)),
            ("login_attempts", "name = ?", (target["name"],)),
            ("team_members", "user_id = ?", (target["id"],)),
            ("activity_logs", "agent = ?", (target["name"],)),
            (
                "approvals",
                "requested_by = ? AND state = 'pending'",
                (target["name"],),
            ),
        ]:
            cur = conn.execute(
                "DELETE FROM %s WHERE %s" % (table, where), params
            )
            counts[table] = cur.rowcount
        # Push tokens belong to the user's devices; remove them too.
        cur = conn.execute("DELETE FROM push_tokens")
        counts["push_tokens"] = cur.rowcount
        cur = conn.execute("DELETE FROM users WHERE id = ?", (target["id"],))
        counts["users"] = cur.rowcount
        conn.execute(
            "INSERT INTO activity_logs (ts, agent, tool, args, ok, error)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                now(),
                actor["name"],
                "account_deletion",
                '{"deleted_user": "%s", "counts": %s}'
                % (target["name"], counts),
                1,
                None,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"deleted": target["name"], "counts": counts}
