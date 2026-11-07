"""ARTHUR MVP — interactive CLI entry point.

Bootstraps sys.path, initializes the DB, runs the FIRST-RUN OWNER SETUP
(prompt for owner name when no admin user exists), then starts the
background Worker and the manager-monitor Scheduler and drops into a REPL.
"""
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEMO_MODE = os.environ.get("DEMO_MODE", "true").lower() == "true"


def _load_llm_client():
    try:
        from backend.llm.client import LLMClient
    except ImportError:  # fallback: llm/ at repo root
        from llm.client import LLMClient  # noqa: F401
    return LLMClient


def main():
    from backend.database.db import init_db, get_admin_user, create_user, get_conn
    from backend.tools.registry import make_registry
    from backend.agents.manager import ManagerAgent
    from backend.tasks.worker import Worker
    from backend.tasks.scheduler import Scheduler
    from backend.tasks.queue import list_projects, list_tasks
    from backend.security.approvals import list_approvals, resolve_approval

    init_db()

    print("ARTHUR \u2014 Autonomous Reasoning & Task Handling Utility Runtime "
          f"(MVP, DEMO_MODE={str(DEMO_MODE)})")

    # ---- FIRST-RUN OWNER SETUP (before the worker starts) ----
    owner = get_admin_user()
    if owner is None:
        try:
            name = input("No owner account found. Enter owner name [Mohammed Farhan]: ").strip()
        except EOFError:
            name = ""
        if not name:
            name = "Mohammed Farhan"
        create_user(name, role="Owner", is_admin=True)
        print(f"Owner '{name}' created with Admin privileges.")
        owner = get_admin_user()

    # ---- OWNER PASSWORD (bcrypt; needed for API auth outside DEMO_MODE) ----
    if not owner.get("password_hash"):
        from backend.security.auth import set_user_password

        env_pw = os.environ.get("ARTHUR_OWNER_PASSWORD", "")
        if env_pw:
            set_user_password(owner["id"], env_pw)
            print("Owner password set from ARTHUR_OWNER_PASSWORD.")
        elif sys.stdin.isatty():
            import getpass

            try:
                pw = getpass.getpass("Set a password for the owner account: ").strip()
            except (EOFError, KeyboardInterrupt):
                pw = ""
            if pw:
                pw2 = getpass.getpass("Confirm password: ").strip()
                if pw == pw2:
                    set_user_password(owner["id"], pw)
                    print("Owner password set.")
                else:
                    print("Passwords did not match — no password set. "
                          "API auth will stay unavailable until you set one.")
            else:
                print("No password set — API auth will stay unavailable "
                      "until you set one (ARTHUR_OWNER_PASSWORD).")
        owner = get_admin_user()

    LLMClient = _load_llm_client()
    registry = make_registry()
    llm = LLMClient()
    manager = ManagerAgent(registry, llm)

    # ---- Background worker (daemon) ----
    worker = Worker()
    worker_thread = threading.Thread(target=worker.start, daemon=True,
                                     name="arthur-worker")
    worker_thread.start()

    # ---- Scheduler: manager monitor tick every 10s ----
    scheduler = Scheduler()
    scheduler.schedule("manager_monitor", 10, manager.monitor_tick)
    scheduler.start()

    print("Worker and scheduler started. Type /quit to exit.")
    try:
        while True:
            try:
                text = input("ARTHUR> ").strip()
            except EOFError:
                break
            if not text:
                continue
            if text == "/quit":
                break
            elif text == "/projects":
                projects = list_projects()
                if not projects:
                    print("(no projects yet)")
                for p in projects:
                    print(f"[{p['id']}] {p['name']} ({p['status']})")
            elif text.startswith("/tasks"):
                parts = text.split()
                pid = int(parts[1]) if len(parts) > 1 else None
                tasks = list_tasks(project_id=pid)
                if not tasks:
                    print("(no tasks)")
                for t in tasks:
                    print(f"[{t['id']}] {t['title']} \u2014 {t['agent']} \u2014 {t['state']}")
            elif text == "/agents":
                conn = get_conn()
                try:
                    rows = conn.execute(
                        "SELECT name, kind, permission_level, status FROM agents "
                        "ORDER BY name").fetchall()
                finally:
                    conn.close()
                for r in rows:
                    print(f"{r['name']} ({r['kind']}, level {r['permission_level']}) \u2014 {r['status']}")
            elif text == "/approvals":
                pending = list_approvals()
                if not pending:
                    print("(no pending approvals)")
                for a in pending:
                    print(f"[{a['id']}] {a['kind']}: {a['subject']} (requested by {a['requested_by']})")
            elif text == "/export":
                import json as _json
                from backend.security.data_rights import export_user_data

                try:
                    data = export_user_data(owner["name"])
                    from backend.database.db import DATA_DIR

                    path = os.path.join(
                        DATA_DIR,
                        f"export-{owner['name']}-{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
                    )
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "w") as f:
                        _json.dump(data, f, indent=2)
                    print(f"Exported your data to {path}")
                except Exception as e:
                    print(f"Error: {e}")
            elif text == "/delete-account":
                from backend.security.data_rights import delete_user_account

                confirm = input(
                    "Type DELETE to permanently delete your account and all "
                    "its data: ").strip()
                if confirm != "DELETE":
                    print("Cancelled.")
                    continue
                try:
                    result = delete_user_account(owner["name"], owner["name"])
                    print(f"Account deleted: {result}")
                    break
                except PermissionError as e:
                    print(f"Permission denied: {e}")
                except Exception as e:
                    print(f"Error: {e}")
            elif text.startswith("/approve"):
                parts = text.split()
                if len(parts) < 2:
                    print("usage: /approve <id>")
                    continue
                try:
                    aid = int(parts[1])
                except ValueError:
                    print("usage: /approve <id>")
                    continue
                try:
                    resolved_by = owner["name"] if owner else ""
                    resolve_approval(aid, True, resolved_by=resolved_by)
                    print(f"Approval {aid} approved by {resolved_by or 'owner'}.")
                except PermissionError as e:
                    print(f"Permission denied: {e}")
                except Exception as e:
                    print(f"Error: {e}")
            else:
                print(manager.handle_goal(text))
    except KeyboardInterrupt:
        print()
    finally:
        try:
            scheduler.stop()
        except Exception:
            pass
        print("ARTHUR shutting down. Goodbye.")


if __name__ == "__main__":
    main()
