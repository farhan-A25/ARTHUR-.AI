"""Worker: claims tasks from the queue and runs them via agents (Builder D)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import time

from backend.database.db import init_db, get_conn, now
try:
    from backend.llm.client import LLMClient
except ImportError:  # fallback: llm/ at repo root
    from llm.client import LLMClient
from backend.tools.registry import make_registry, WaitingForApproval
from backend.agents.researcher import ResearcherAgent
from backend.agents.developer import DeveloperAgent
from backend.agents.qa import QAAgent
from backend.agents.browser import BrowserAgent
from backend.agents.analyst import AnalystAgent
from backend.tasks import queue as q

TERMINAL_STATES = ("COMPLETED", "FAILED")


def agent_factory(registry, llm):
    """Build the agent map the worker dispatches to."""
    return {
        "researcher": ResearcherAgent(registry=registry, llm=llm),
        "developer": DeveloperAgent(registry=registry, llm=llm),
        "qa": QAAgent(registry=registry, llm=llm),
        "browser": BrowserAgent(registry=registry, llm=llm),
        "analyst": AnalystAgent(registry=registry, llm=llm),
    }


class Worker:
    def __init__(self):
        init_db()
        self.registry = make_registry()
        self.llm = LLMClient()
        self.agents = agent_factory(self.registry, self.llm)

    def start(self, stop_event=None):
        """Main loop: recover once, then claim + run until stopped."""
        q.recover_running()
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            task = q.claim_next()
            if task:
                self.run_task(task)
            else:
                time.sleep(2)

    def run_task(self, task):
        """Run one claimed task to a terminal disposition for this attempt."""
        agent = self.agents.get(task["agent"])
        agent_name = agent.name if agent is not None else task["agent"]
        run_id = self._run_start(task["id"], agent_name)
        ok = True
        output = ""
        try:
            if agent is None:
                raise RuntimeError("unknown agent: %r" % (task["agent"],))
            res = agent.run(task) or {}
            if res.get("ok"):
                q.set_state(task["id"], "COMPLETED", result=res)
                output = str(res.get("output", ""))[:2000]
                self._maybe_push_project_done(task)
            else:
                err = res.get("error") or "agent returned ok=False"
                updated = q.retry_or_fail(task["id"], err)
                output = err[:2000]
                ok = False
                if updated["state"] == "FAILED":
                    self._send_push("ARTHUR: task failed", task["title"],
                                    {"task_id": task["id"],
                                     "project_id": task["project_id"]})
        except WaitingForApproval as e:
            q.set_state(task["id"], "WAITING_FOR_APPROVAL",
                        error="approval:%s" % (e.approval_id,))
            output = "waiting for approval %s" % (e.approval_id,)
            ok = False
        except Exception as e:  # never let one task kill the worker loop
            err = "%s: %s" % (type(e).__name__, e)
            try:
                updated = q.retry_or_fail(task["id"], err)
            except Exception:
                updated = {"state": "?"}
            output = err[:2000]
            ok = False
            if updated.get("state") == "FAILED":
                self._send_push("ARTHUR: task failed", task["title"],
                                {"task_id": task["id"],
                                 "project_id": task["project_id"]})
        finally:
            self._run_end(run_id, ok, output)

    # ------------------------------------------------------------------
    # agent_runs bookkeeping
    # ------------------------------------------------------------------

    @staticmethod
    def _run_start(task_id, agent_name):
        conn = get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO agent_runs (agent_name, task_id, started_at, "
                "ended_at, ok, output) VALUES (?, ?, ?, NULL, NULL, NULL)",
                (agent_name, task_id, now()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    @staticmethod
    def _run_end(run_id, ok, output):
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE agent_runs SET ended_at = ?, ok = ?, output = ? "
                "WHERE id = ?",
                (now(), 1 if ok else 0, (output or "")[:4000], run_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # push notifications (fire-and-forget; never raise)
    # ------------------------------------------------------------------

    @staticmethod
    def _send_push(title, body, data):
        try:
            from backend.api.notify import send_push
        except ImportError:
            return  # Builder E's module not present yet -> skip silently
        try:
            send_push(title, body, data)
        except Exception:
            pass

    def _maybe_push_project_done(self, task):
        project_id = task["project_id"]
        try:
            tasks = q.list_tasks(project_id)
            if not tasks:
                return
            if all(t["state"] in TERMINAL_STATES for t in tasks):
                conn = get_conn()
                try:
                    row = conn.execute(
                        "SELECT name FROM projects WHERE id = ?",
                        (project_id,)).fetchone()
                finally:
                    conn.close()
                name = row["name"] if row else "project %s" % project_id
                self._send_push("ARTHUR: project completed", name,
                                {"project_id": project_id})
        except Exception:
            pass


if __name__ == "__main__":
    Worker().start()
