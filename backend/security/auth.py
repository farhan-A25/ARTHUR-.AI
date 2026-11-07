"""ARTHUR authentication: passwords, sessions, rate limiting, lockout.

- Passwords: bcrypt hashing (``hash_password`` / ``verify_password``).
  The ``users`` table carries ``password_hash`` (added by migration).
- Sessions: random 256-bit tokens (``secrets.token_urlsafe``), stored as
  SHA-256 hashes in the ``sessions`` table with an expiry
  (``ARTHUR_SESSION_HOURS``, default 24). ``validate_session`` returns the
  user dict or None.
- Rate limiting: max 5 login attempts per minute per IP (429 afterwards).
- Lockout: 10 failed logins in 15 minutes for an IP+name pair locks that
  pair out for 15 minutes (403 with retry hint).

All failures are recorded in ``login_attempts``; nothing secret is logged
(values pass through the scrubber at the call site).
"""
from __future__ import annotations

import datetime
import hashlib
import os
import secrets as _pysecrets

from backend.database.db import get_conn, get_user_by_name, now

SESSION_HOURS = float(os.environ.get("ARTHUR_SESSION_HOURS", "24"))
RATE_LIMIT_PER_MINUTE = 5
LOCKOUT_FAILURES = 10
LOCKOUT_WINDOW_SECONDS = 15 * 60
LOCKOUT_DURATION_SECONDS = 15 * 60


# ----------------------------------------------------------------------------
# Passwords (bcrypt)
# ----------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """bcrypt-hash ``password``. Raises ValueError on empty password."""
    import bcrypt

    if not password:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, pw_hash: str) -> bool:
    """True when ``password`` matches the bcrypt ``pw_hash``."""
    import bcrypt

    if not password or not pw_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), pw_hash.encode())
    except Exception:
        return False


def set_user_password(user_id: int, password: str) -> None:
    """Set (or reset) a user's bcrypt password hash."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Sessions
# ----------------------------------------------------------------------------
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> tuple[str, str]:
    """Create a session; returns (raw_token, expires_at ISO)."""
    token = _pysecrets.token_urlsafe(32)
    expires = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=SESSION_HOURS)
    ).isoformat()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at,"
            " revoked) VALUES (?, ?, ?, ?, 0)",
            (_token_hash(token), user_id, now(), expires),
        )
        conn.commit()
    finally:
        conn.close()
    return token, expires


def validate_session(token: str) -> dict | None:
    """Return the user dict for a live session token, else None."""
    if not token:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT s.*, u.name, u.role, u.is_admin FROM sessions s"
            " JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = ? AND s.revoked = 0",
            (_token_hash(token),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    if row["expires_at"] < now():
        return None
    return {
        "id": row["user_id"],
        "name": row["name"],
        "role": row["role"],
        "is_admin": bool(row["is_admin"]),
    }


def revoke_session(token: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE sessions SET revoked = 1 WHERE token_hash = ?",
            (_token_hash(token),),
        )
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Rate limiting + lockout
# ----------------------------------------------------------------------------
def _window_cutoff(seconds: int) -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(seconds=seconds)
    ).isoformat()


def record_login_attempt(ip: str, name: str, ok: bool) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO login_attempts (ip, name, ts, ok) VALUES (?, ?, ?, ?)",
            (ip or "", name or "", now(), 1 if ok else 0),
        )
        conn.commit()
    finally:
        conn.close()


def check_rate_limit(ip: str) -> bool:
    """True if ``ip`` is still within 5 attempts/minute."""
    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM login_attempts WHERE ip = ? AND ts > ?",
            (ip or "", _window_cutoff(60)),
        ).fetchone()["c"]
    finally:
        conn.close()
    return n < RATE_LIMIT_PER_MINUTE


def lockout_until(ip: str, name: str) -> str | None:
    """ISO timestamp until which (ip, name) is locked, or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT ts FROM login_attempts WHERE ip = ? AND name = ? AND ok = 0"
            " AND ts > ? ORDER BY ts DESC LIMIT 1",
            (ip or "", name or "", _window_cutoff(LOCKOUT_WINDOW_SECONDS)),
        ).fetchone()
        if row is None:
            return None
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM login_attempts WHERE ip = ? AND name = ?"
            " AND ok = 0 AND ts > ?",
            (ip or "", name or "", _window_cutoff(LOCKOUT_WINDOW_SECONDS)),
        ).fetchone()["c"]
    finally:
        conn.close()
    if n < LOCKOUT_FAILURES:
        return None
    locked_until = (
        datetime.datetime.fromisoformat(row["ts"])
        + datetime.timedelta(seconds=LOCKOUT_DURATION_SECONDS)
    ).isoformat()
    return locked_until if locked_until > now() else None


def authenticate(name: str, password: str) -> dict | None:
    """Return the user dict when credentials are valid, else None."""
    user = get_user_by_name(name)
    if user is None:
        return None
    if not verify_password(password, user.get("password_hash") or ""):
        return None
    return user
