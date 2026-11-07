"""ARTHUR secrets: encrypted-at-rest storage + log scrubbing.

- Secrets (API keys, tokens) are stored Fernet-encrypted. The Fernet key
  comes from ``ARTHUR_SECRET_KEY`` (base64url 32 bytes); if unset, a key is
  generated once and saved to ``$ARTHUR_HOME/.arthur_secret`` (mode 600).
- ``scrub()`` redacts key-like values from any text before it reaches logs,
  chat history, or error messages. ``install_scrubbing()`` attaches the
  redaction as a logging filter on the root logger.

NEVER log, chat, or surface raw secret values — always pass them through
``scrub()`` first.
"""
from __future__ import annotations

import base64
import logging
import os
import re

from backend.database.db import ARTHUR_HOME, get_conn, now

_SECRET_FILE = os.path.join(ARTHUR_HOME, ".arthur_secret")

# ----------------------------------------------------------------------------
# Fernet key management
# ----------------------------------------------------------------------------
def _load_or_create_key() -> bytes:
    """Return the raw 32-byte secret key (env first, then file, then create)."""
    env_key = os.environ.get("ARTHUR_SECRET_KEY", "").strip()
    if env_key:
        try:
            raw = base64.urlsafe_b64decode(env_key + "=" * (-len(env_key) % 4))
            if len(raw) == 32:
                return raw
        except Exception:
            pass  # fall through to file key
    if os.path.exists(_SECRET_FILE):
        with open(_SECRET_FILE, "r") as f:
            raw = base64.urlsafe_b64decode(f.read().strip())
            if len(raw) == 32:
                return raw
    raw = os.urandom(32)
    os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
    fd = os.open(_SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(base64.urlsafe_b64encode(raw).decode())
    try:
        os.chmod(_SECRET_FILE, 0o600)
    except OSError:
        pass
    return raw


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(base64.urlsafe_b64encode(_load_or_create_key()))


def encrypt_secret(plaintext: str) -> str:
    """Fernet-encrypt a secret string. Returns the token string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a value produced by :func:`encrypt_secret`."""
    return _fernet().decrypt(token.encode()).decode()


# ----------------------------------------------------------------------------
# Encrypted secret store (SQLite `secrets` table)
# ----------------------------------------------------------------------------
def store_secret(name: str, value: str) -> None:
    """Store ``name`` encrypted at rest (upsert)."""
    enc = encrypt_secret(value)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO secrets (name, value_enc, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET value_enc=excluded.value_enc,"
            " updated_at=excluded.updated_at",
            (name, enc, now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_secret(name: str) -> str | None:
    """Return the decrypted secret for ``name``, or None if not stored."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value_enc FROM secrets WHERE name = ?", (name,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return decrypt_secret(row["value_enc"])


def delete_secret(name: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM secrets WHERE name = ?", (name,))
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Log / chat / error scrubbing
# ----------------------------------------------------------------------------
_SCRUB_PATTERNS = [
    # OpenAI-style keys and generic long key-like tokens
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"), "sk-[REDACTED]"),
    # Expo push tokens
    (re.compile(r"ExponentPushToken\[[^\]]*\]"), "ExponentPushToken[[REDACTED]]"),
    # KEY=VALUE / "key": "value" assignments for key-ish names
    # (optional quotes around the key, for JSON payloads too)
    (
        re.compile(
            r"(?i)['\"]?\b([a-z0-9_.\-]*?(?:api[_-]?key|secret|passwd|password|token)"
            r"[a-z0-9_.\-]*)\b['\"]?\s*[:=]\s*['\"]?([^'\"\s,}]+)['\"]?"
        ),
        r"\1=[REDACTED]",
    ),
    # Bearer tokens in headers
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9_\-.~+/=]{8,}"), r"\1 [REDACTED]"),
    # ARTHUR_*KEY=... env-style lines
    (
        re.compile(r"\b(ARTHUR_[A-Z_]*(?:KEY|SECRET|PASSWORD|TOKEN))\s*=\s*\S+"),
        r"\1=[REDACTED]",
    ),
]


def scrub(text) -> str:
    """Redact secret-looking values from ``text``. Non-strings pass through."""
    if not isinstance(text, str):
        return text
    for pattern, repl in _SCRUB_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def scrub_dict(d: dict) -> dict:
    """Return a copy of ``d`` with secret-looking values redacted."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = scrub_dict(v)
        elif isinstance(v, str) and re.search(
            r"(?i)(key|secret|password|passwd|token)", str(k)
        ):
            out[k] = "[REDACTED]"
        elif isinstance(v, str):
            out[k] = scrub(v)
        else:
            out[k] = v
    return out


class _ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = scrub_dict(record.args)
                else:
                    record.args = tuple(scrub(a) for a in record.args)
        except Exception:
            pass
        return True


def install_scrubbing() -> None:
    """Attach secret-redaction to the root logger (idempotent)."""
    root = logging.getLogger()
    if not any(isinstance(f, _ScrubFilter) for f in root.filters):
        root.addFilter(_ScrubFilter())
