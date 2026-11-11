"""ARTHUR task queue: projects, tasks, atomic claiming, retries, checkpoints."""

import datetime
import json

from backend.database.db import USING_POSTGRES, get_conn, now
from backend.memory.store import update_project_profile

STATES = (
    "CREATED",
    "PLANNING",
    "QUEUED",
    "RUNNING",
    "WAITING_FOR_TOOL",
    "WAITING_FOR_APPROVAL",
    "TESTING",
    "FAILED",
    "RETRYING",
    "COMPLETED",
)

TERMINAL_STATES = ("FAILED", "COMPLETED")

RETRY_BASE_SECONDS = 5


def _task_dict(row):
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "agent": row["agent"],
        "deps": json.loads(row["deps"] or "[]"),
        "state": row["state"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "checkpoint": json.loads(row["checkpoint"] or "{}"),
        "result": json.loads(row["result"]) if row["result"] else None,
        "error": row["error"],
        "success_criteria": row["success_criteria"],
        "steps": json.loads(row["steps"] or "[]"),
        "next_retry_at": row["next_retry_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _project_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "completion_conditions": json.loads(row["completion_conditions"] or "[]"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_project(name, description="", completion_conditions=None):
    """Create a project row, refresh its memory profile, return the id."""
    conditions = list(completion_conditions) if completion_conditions else []
    conn = get_conn()
    try:
        n = now()
        cur = conn.execute(
            """INSERT INTO projects(name, description, status, completion_conditions,
                                    created_at, updated_at)
               VALUES (?, ?, 'active', ?, ?, ?)""",
            (name, description, json.dumps(conditions), n, n),
        )
        project_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    update_project_profile(
        project_id,
        {
            "name": name,
            "description": description,
            "status": "active",
            "completion_conditions": conditions,
        },
    )
    return project_id


def list_projects():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM projects ORDER BY id ASC").fetchall()
        return [_project_dict(r) for r in rows]
    finally:
        conn.close()


def create_task(project_id, title, agent, deps=None, success_criteria="",
                steps=None, max_attempts=3):
    """Create a task in CREATED state; return the new task id."""
    conn = get_conn()
    try:
        n = now()
        cur = conn.execute(
            """INSERT INTO tasks(project_id, title, agent, deps, state, attempts,
                                 max_attempts, checkpoint, success_criteria, steps,
                                 created_at, updated_at)
               VALUES (?, ?, ?, ?, 'CREATED', 0, ?, '{}', ?, ?, ?, ?)""",
            (
                project_id,
                title,
                agent,
                json.dumps(list(deps) if deps else []),
                max_attempts,
                success_criteria or "",
                json.dumps(list(steps) if steps else []),
                n,
                n,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_task(task_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError("task %r not found" % (task_id,))
        return _task_dict(row)
    finally:
        conn.close()


def list_tasks(project_id=None, state=None):
    sql = "SELECT * FROM tasks"
    clauses, params = [], []
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)
    if state is not None:
        clauses.append("state = ?")
        params.append(state)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id ASC"
    conn = get_conn()
    try:
        return [_task_dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def claim_next():
    """Atomically claim the oldest runnable task.

    Eligible: QUEUED, or RETRYING with next_retry_at <= now, and all deps
    in COMPLETED. The claimed task is set to RUNNING and returned as a dict;
    returns None when nothing is runnable.
    """
    conn = get_conn()
    try:
        conn.isolation_level = None  # manual transaction control
        conn.execute("BEGIN IMMEDIATE")
        n = now()
        # On Postgres, BEGIN IMMEDIATE becomes a plain BEGIN, which no
        # longer serialises claimers by itself — lock the candidate rows
        # instead so two workers cannot claim the same task. (SQLite
        # keeps the original BEGIN IMMEDIATE behaviour.)
        lock = " FOR UPDATE SKIP LOCKED" if USING_POSTGRES else ""
        rows = conn.execute(
            """SELECT * FROM tasks
               WHERE state = 'QUEUED'
                  OR (state = 'RETRYING' AND next_retry_at <= ?)
               ORDER BY id ASC""" + lock,
            (n,),
        ).fetchall()
        chosen = None
        for row in rows:
            deps = json.loads(row["deps"] or "[]")
            runnable = True
            for dep_id in deps:
                dep = conn.execute(
                    "SELECT state FROM tasks WHERE id = ?", (dep_id,)
                ).fetchone()
                if dep is None or dep["state"] != "COMPLETED":
                    runnable = False
                    break
            if runnable:
                chosen = row
                break
        if chosen is None:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE tasks SET state = 'RUNNING', updated_at = ? WHERE id = ?",
            (n, chosen["id"]),
        )
        conn.execute("COMMIT")
        task_id = chosen["id"]
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return get_task(task_id)


def set_state(task_id, state, error=None, result=None):
    """Set a task's state (must be one of STATES); optionally store error/result."""
    if state not in STATES:
        raise ValueError("unknown task state %r; expected one of %s" % (state, STATES))
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE tasks SET state = ?, error = ?, result = ?, updated_at = ? WHERE id = ?",
            (
                state,
                error,
                json.dumps(result) if result is not None else None,
                now(),
                task_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_checkpoint(task_id, step_index, data=None):
    """Merge {"step_index": n, "data": {...}} into the task's checkpoint JSON."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT checkpoint FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError("task %r not found" % (task_id,))
        checkpoint = json.loads(row["checkpoint"] or "{}")
        checkpoint["step_index"] = step_index
        checkpoint["data"] = data if data is not None else {}
        conn.execute(
            "UPDATE tasks SET checkpoint = ?, updated_at = ? WHERE id = ?",
            (json.dumps(checkpoint), now(), task_id),
        )
        conn.commit()
        return checkpoint
    finally:
        conn.close()


def retry_or_fail(task_id, error):
    """Record a failure: attempts += 1; RETRYING with exponential backoff,
    or FAILED once max_attempts is reached."""
    task = get_task(task_id)
    attempts = task["attempts"] + 1
    conn = get_conn()
    try:
        if attempts >= task["max_attempts"]:
            conn.execute(
                "UPDATE tasks SET attempts = ?, state = 'FAILED', error = ?, updated_at = ? WHERE id = ?",
                (attempts, error, now(), task_id),
            )
        else:
            backoff = RETRY_BASE_SECONDS * (2 ** attempts)
            retry_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(seconds=backoff)
            ).isoformat()
            conn.execute(
                """UPDATE tasks SET attempts = ?, state = 'RETRYING',
                                  error = ?, next_retry_at = ?, updated_at = ?
                   WHERE id = ?""",
                (attempts, error, retry_at, now(), task_id),
            )
        conn.commit()
    finally:
        conn.close()
    return get_task(task_id)


def requeue_with_fix(task_id, fix_note):
    """Reset attempts, append fix_note to checkpoint['fix_notes'], QUEUED."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT checkpoint FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError("task %r not found" % (task_id,))
        checkpoint = json.loads(row["checkpoint"] or "{}")
        notes = checkpoint.get("fix_notes") or []
        notes.append(fix_note)
        checkpoint["fix_notes"] = notes
        conn.execute(
            """UPDATE tasks SET attempts = 0, state = 'QUEUED',
                              checkpoint = ?, updated_at = ? WHERE id = ?""",
            (json.dumps(checkpoint), now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()


def recover_running():
    """Crash recovery: move every RUNNING task back to RETRYING (retry now)."""
    conn = get_conn()
    try:
        n = now()
        cur = conn.execute(
            "UPDATE tasks SET state = 'RETRYING', next_retry_at = ?, updated_at = ? WHERE state = 'RUNNING'",
            (n, n),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
