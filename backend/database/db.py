"""ARTHUR persistence core: paths, connections, schema, and seeding.

Imports NOTHING from other backend modules (stdlib only). Every other
module reaches the DB through this one.
"""

import datetime
import json
import os
import sqlite3

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTHUR_HOME = os.environ.get("ARTHUR_HOME", REPO_ROOT)
DATA_DIR = os.path.join(ARTHUR_HOME, "data")
DB_PATH = os.environ.get("ARTHUR_DB_PATH", os.path.join(DATA_DIR, "arthur.db"))


def now():
    """UTC ISO-8601 timestamp string (the canonical timestamp format)."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def get_conn():
    """Open a SQLite connection: DATA_DIR created, Row factory, FK on.

    The database file is chmod 600 (owner read/write only) on every open —
    best effort, ignored where the platform forbids it.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if os.path.exists(DB_PATH):
            os.chmod(DB_PATH, 0o600)
    except OSError:
        pass
    return conn


# ----------------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------------
_TABLES = [
    """CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        name TEXT,
        role TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS teams(
        id INTEGER PRIMARY KEY,
        name TEXT,
        created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS team_members(
        id INTEGER PRIMARY KEY,
        team_id INTEGER,
        user_id INTEGER,
        role TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        description TEXT,
        status TEXT DEFAULT 'active',
        completion_conditions TEXT,
        created_at TEXT,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY,
        project_id INTEGER,
        title TEXT,
        agent TEXT,
        deps TEXT,
        state TEXT DEFAULT 'CREATED',
        attempts INTEGER DEFAULT 0,
        max_attempts INTEGER DEFAULT 3,
        checkpoint TEXT,
        result TEXT,
        error TEXT,
        success_criteria TEXT DEFAULT '',
        steps TEXT,
        next_retry_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS agents(
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        kind TEXT,
        permission_level INTEGER,
        status TEXT DEFAULT 'idle'
    )""",
    """CREATE TABLE IF NOT EXISTS agent_runs(
        id INTEGER PRIMARY KEY,
        agent_name TEXT,
        task_id INTEGER,
        started_at TEXT,
        ended_at TEXT,
        ok INTEGER,
        output TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY,
        project_id INTEGER,
        role TEXT,
        content TEXT,
        created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS memories(
        id INTEGER PRIMARY KEY,
        kind TEXT,
        key TEXT,
        value TEXT,
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(kind, key)
    )""",
    """CREATE TABLE IF NOT EXISTS documents(
        id INTEGER PRIMARY KEY,
        project_id INTEGER,
        title TEXT,
        content TEXT,
        created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS tools(
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        permission_level INTEGER,
        description TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS tool_permissions(
        id INTEGER PRIMARY KEY,
        agent_name TEXT,
        tool_name TEXT,
        allowed INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS approvals(
        id INTEGER PRIMARY KEY,
        kind TEXT,
        subject TEXT,
        detail TEXT,
        state TEXT DEFAULT 'pending',
        requested_by TEXT,
        created_at TEXT,
        resolved_at TEXT,
        resolved_by TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS activity_logs(
        id INTEGER PRIMARY KEY,
        ts TEXT,
        agent TEXT,
        tool TEXT,
        args TEXT,
        ok INTEGER,
        error TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS push_tokens(
        id INTEGER PRIMARY KEY,
        token TEXT UNIQUE,
        platform TEXT,
        created_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS secrets(
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        value_enc TEXT,
        updated_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS sessions(
        id INTEGER PRIMARY KEY,
        token_hash TEXT UNIQUE,
        user_id INTEGER,
        created_at TEXT,
        expires_at TEXT,
        revoked INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS login_attempts(
        id INTEGER PRIMARY KEY,
        ip TEXT,
        name TEXT,
        ts TEXT,
        ok INTEGER DEFAULT 0
    )""",
]


def _init_fts(conn):
    """Create the memories_fts FTS5 table + sync triggers.

    Returns True when FTS5 is available; False when the SQLite build lacks
    the FTS5 module (search_memories() then falls back to LIKE).
    """
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(key, value)")
    except sqlite3.OperationalError:
        return False
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories
           BEGIN
             INSERT INTO memories_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
           END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories
           BEGIN
             UPDATE memories_fts SET key = new.key, value = new.value WHERE rowid = new.id;
           END"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories
           BEGIN
             DELETE FROM memories_fts WHERE rowid = old.id;
           END"""
    )
    # Backfill any rows that predate the FTS table (idempotent).
    conn.execute(
        """INSERT INTO memories_fts(rowid, key, value)
           SELECT id, key, value FROM memories
           WHERE id NOT IN (SELECT rowid FROM memories_fts)"""
    )
    return True


# ----------------------------------------------------------------------------
# Seeding
# ----------------------------------------------------------------------------
_SEED_AGENTS = [
    ("manager", "manager", 2),
    ("researcher", "researcher", 0),
    ("developer", "developer", 1),
    ("browser", "browser", 1),
    ("analyst", "analyst", 1),
    ("qa", "qa", 1),
]


def _seed(conn):
    owner_name = os.environ.get("ARTHUR_OWNER_NAME", "Mohammed Farhan")
    existing_admin = conn.execute("SELECT id FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    if existing_admin is None:
        conn.execute(
            "INSERT INTO users(name, role, is_admin, created_at) VALUES (?, 'Owner', 1, ?)",
            (owner_name, now()),
        )
    for name, kind, level in _SEED_AGENTS:
        conn.execute(
            "INSERT OR IGNORE INTO agents(name, kind, permission_level, status) VALUES (?, ?, ?, 'idle')",
            (name, kind, level),
        )


def _migrate(conn):
    """Idempotent schema migrations for databases created before a column.

    Currently: adds ``users.password_hash`` (bcrypt) when missing.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "password_hash" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")


def init_db():
    """Create all tables (idempotent) and seed owner + agents."""
    conn = get_conn()
    try:
        for ddl in _TABLES:
            conn.execute(ddl)
        _init_fts(conn)
        _migrate(conn)
        _seed(conn)
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# User helpers — SOLE-ADMIN GUARANTEE
#
# The owner account is the ONE AND ONLY admin. There are no built-in,
# default, backdoor, "system", "assistant", or agent admin accounts, and no
# code path may create one. Only the existing admin can change roles, and
# even the admin cannot create a second admin or demote the owner (that
# would violate "exactly one admin"). Every role change is audit-logged.
# ----------------------------------------------------------------------------
def get_user_by_name(name):
    """Return a user dict by name, or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE name = ? LIMIT 1", (name,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _audit_role_change(conn, actor_name, user_id, old, new):
    conn.execute(
        "INSERT INTO activity_logs (ts, agent, tool, args, ok, error)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            now(),
            actor_name,
            "role_change",
            json.dumps(
                {
                    "user_id": user_id,
                    "old": old,
                    "new": new,
                }
            ),
            1,
            None,
        ),
    )


def create_user(name, role="member", is_admin=False):
    """Insert a user row; returns the new user id.

    Sole-admin enforcement: is_admin=True is honored ONLY when no admin
    exists yet (first-run bootstrap). Otherwise a second admin can never
    be created — PermissionError is raised.
    """
    conn = get_conn()
    try:
        if is_admin:
            existing = conn.execute(
                "SELECT id FROM users WHERE is_admin = 1 LIMIT 1"
            ).fetchone()
            if existing is not None:
                raise PermissionError(
                    "sole-admin guarantee: an admin already exists; refusing"
                    " to create a second admin account"
                )
        cur = conn.execute(
            "INSERT INTO users(name, role, is_admin, created_at) VALUES (?, ?, ?, ?)",
            (name, role, 1 if is_admin else 0, now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_user_role(user_id, role=None, is_admin=None, actor_name=""):
    """Change a user's role / admin flag. Admin-actor only; audited.

    Rules (sole-admin guarantee):
    - actor_name must name the existing admin, else PermissionError.
    - is_admin=True for anyone but the current sole admin -> PermissionError
      (no second admin, no self-promotion by agents or users).
    - The sole admin can never be demoted (is_admin=False refused).
    - Every change appends an activity_logs row with actor, timestamp,
      and the old->new diff.
    Returns the updated user dict.
    """
    conn = get_conn()
    try:
        actor = conn.execute(
            "SELECT * FROM users WHERE name = ? LIMIT 1", (actor_name,)
        ).fetchone()
        if actor is None or not actor["is_admin"]:
            raise PermissionError(
                "only the owner/admin may change roles (actor=%r)" % (actor_name,)
            )
        target = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            raise KeyError("user %s not found" % (user_id,))
        target = dict(target)
        sole_admin = conn.execute(
            "SELECT * FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
        ).fetchone()
        sole_admin_id = sole_admin["id"] if sole_admin else None

        new_role = target["role"] if role is None else role
        new_admin = bool(target["is_admin"]) if is_admin is None else bool(is_admin)
        if new_admin and target["id"] != sole_admin_id:
            raise PermissionError(
                "sole-admin guarantee: only the owner account may hold admin"
            )
        if not new_admin and target["id"] == sole_admin_id:
            raise PermissionError(
                "sole-admin guarantee: the owner/admin account cannot be demoted"
            )
        old = {"role": target["role"], "is_admin": bool(target["is_admin"])}
        new = {"role": new_role, "is_admin": new_admin}
        conn.execute(
            "UPDATE users SET role = ?, is_admin = ? WHERE id = ?",
            (new_role, 1 if new_admin else 0, user_id),
        )
        _audit_role_change(conn, actor["name"], user_id, old, new)
        conn.commit()
        return get_user_by_name(target["name"])
    finally:
        conn.close()


def get_admin_user():
    """Return the first user with is_admin=1 as a dict, or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE is_admin = 1 ORDER BY id ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
