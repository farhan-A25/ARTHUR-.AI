"""Approval queue: create, list, get, resolve approvals.

Resolving an approval requires admin privileges. ``resolved_by`` names a
user; the user is looked up by name and must have is_admin=1, otherwise
PermissionError is raised. An empty ``resolved_by`` (single-owner CLI
context) resolves to the admin owner; if no admin user exists,
PermissionError("no admin user") is raised.
"""
from __future__ import annotations

import json

from backend.database.db import get_admin_user, get_conn, now
from backend.security.permissions import require_admin_user as require_admin


def _audit(conn, agent, tool, args, ok, error=None):
    conn.execute(
        "INSERT INTO activity_logs (ts, agent, tool, args, ok, error)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (now(), agent, tool, json.dumps(args), 1 if ok else 0, error),
    )


def _notify_push(title, body, data):
    """Fire-and-forget push notification. Never raises.

    backend/api/notify.py is owned by another builder; if it is missing
    (or send_push fails), silently skip.
    """
    try:
        from backend.api.notify import send_push  # lazy: avoid import risk
    except ImportError:
        return
    try:
        send_push(title, body, data)
    except Exception:
        pass


def create_approval(kind, subject, detail, requested_by=""):
    """Create a pending approval. Returns the new approval id."""
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO approvals (kind, subject, detail, state, requested_by,"
            " created_at) VALUES (?, ?, ?, 'pending', ?, ?)",
            (kind, subject, json.dumps(detail), requested_by, now()),
        )
        conn.commit()
        approval_id = cur.lastrowid
    finally:
        conn.close()
    _notify_push(
        "ARTHUR: approval needed", subject, {"approval_id": approval_id}
    )
    return approval_id


def list_approvals(state="pending"):
    """List approvals filtered by state (default: pending)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE state = ? ORDER BY id", (state,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_approval(approval_id):
    """Return a single approval dict, or None if not found."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _parse_detail(detail):
    try:
        return json.loads(detail) if detail else {}
    except Exception:
        return {}


def resolve_approval(approval_id, approved, resolved_by=""):
    """Resolve an approval (approved=True/False).

    Raises PermissionError if ``resolved_by`` names a non-admin user (or a
    user that does not exist). With ``resolved_by=""``, resolves to the
    admin owner; raises PermissionError("no admin user") if none exists.
    """
    conn = get_conn()
    try:
        if resolved_by:
            user = require_admin(resolved_by)
            resolver_name = user["name"]
        else:
            user = get_admin_user()
            if user is None:
                raise PermissionError("no admin user")
            resolver_name = user["name"]

        cur = conn.execute(
            "UPDATE approvals SET state = ?, resolved_at = ?, resolved_by = ?"
            " WHERE id = ?",
            ("approved" if approved else "rejected", now(), resolver_name,
             approval_id),
        )
        if cur.rowcount == 0:
            raise KeyError("approval %s not found" % (approval_id,))
        _audit(
            conn,
            resolver_name,
            "approval_resolution",
            {
                "approval_id": approval_id,
                "old_state": "pending",
                "new_state": "approved" if approved else "rejected",
            },
            True,
        )
        conn.commit()
        approval = get_approval(approval_id)
    finally:
        conn.close()
    _notify_push(
        "ARTHUR: approval " + ("approved" if approved else "denied"),
        approval["subject"] if approval else "",
        {"approval_id": approval_id},
    )
    return approval
