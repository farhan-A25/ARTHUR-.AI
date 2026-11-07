"""ARTHUR long-term memory: key/value store with FTS5 full-text search."""

import json
import sqlite3

from backend.database.db import get_conn, now


def remember(kind, key, value):
    """Upsert a memory by (kind, key). value must be JSON-serializable."""
    payload = json.dumps(value)
    n = now()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO memories(kind, key, value, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(kind, key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = excluded.updated_at""",
            (kind, key, payload, n, n),
        )
        conn.commit()
    finally:
        conn.close()


def recall(kind, key):
    """Return the stored value for (kind, key), or None if absent."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM memories WHERE kind = ? AND key = ?",
            (kind, key),
        ).fetchone()
        if row is None or row["value"] is None:
            return None
        return json.loads(row["value"])
    finally:
        conn.close()


def forget(kind, key):
    """Delete the memory for (kind, key) if it exists."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM memories WHERE kind = ? AND key = ?", (kind, key))
        conn.commit()
    finally:
        conn.close()


def _fts_available(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memories_fts'"
    ).fetchone()
    return row is not None


def search_memories(query, kind=None, limit=10):
    """Full-text search over memory key/value.

    Uses the memories_fts FTS5 table; falls back to LIKE matching when
    FTS5 is unavailable or the MATCH query fails. Returns a list of
    {"kind", "key", "value"} with value JSON-decoded.
    """
    conn = get_conn()
    try:
        results = []
        if _fts_available(conn):
            try:
                sql = (
                    "SELECT m.kind AS kind, m.key AS key, m.value AS value "
                    "FROM memories m JOIN memories_fts ON m.id = memories_fts.rowid "
                    "WHERE memories_fts MATCH ?"
                )
                params = [query]
                if kind is not None:
                    sql += " AND m.kind = ?"
                    params.append(kind)
                sql += " ORDER BY rank LIMIT ?"
                params.append(limit)
                for row in conn.execute(sql, params):
                    results.append(
                        {"kind": row["kind"], "key": row["key"],
                         "value": json.loads(row["value"])}
                    )
                return results
            except sqlite3.Error:
                pass  # fall through to LIKE
        like = "%" + query + "%"
        sql = "SELECT kind, key, value FROM memories WHERE (key LIKE ? OR value LIKE ?)"
        params = [like, like]
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        for row in conn.execute(sql, params):
            results.append(
                {"kind": row["kind"], "key": row["key"], "value": json.loads(row["value"])}
            )
        return results
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Project profiles
# ----------------------------------------------------------------------------
def _profile_key(project_id):
    return "profile:%s" % project_id


def get_project_profile(project_id):
    """Return the project profile dict (default {} if none stored)."""
    return recall("project", _profile_key(project_id)) or {}


def update_project_profile(project_id, updates):
    """Merge `updates` into the project profile and persist it."""
    profile = get_project_profile(project_id)
    profile.update(updates)
    remember("project", _profile_key(project_id), profile)
    return profile
