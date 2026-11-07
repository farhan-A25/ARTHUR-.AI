# ARTHUR MVP — Module Contracts (READ FIRST, follow exactly)

All paths under `~/workspace/arthur-ai/`. Python 3.10+.

## Global conventions
- Every module imports siblings as `from backend.xxx import yyy` (absolute from repo root).
- Entry points (`backend/main.py`, `backend/api/server.py`, `backend/tasks/worker.py`) must bootstrap sys.path FIRST:
  ```python
  import os, sys
  ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  if ROOT not in sys.path: sys.path.insert(0, ROOT)
  ```
  (`ROOT` = `~/workspace/arthur-ai/`.)
- `ARTHUR_HOME`: env override else repo root. Canonical helper lives in `backend/database/db.py`:
  ```python
  ARTHUR_HOME = os.environ.get("ARTHUR_HOME", <repo root>)
  DATA_DIR = os.path.join(ARTHUR_HOME, "data")
  DB_PATH = os.environ.get("ARTHUR_DB_PATH", os.path.join(DATA_DIR, "arthur.db"))
  ```
  All other modules: `from backend.database.db import ARTHUR_HOME, DATA_DIR, DB_PATH`.
- `db.py` imports NOTHING from other backend modules (stdlib `sqlite3`, `os`, `json`, `datetime` only). No circular imports, ever.
- `DEMO_MODE`: `os.environ.get("DEMO_MODE", "true").lower() == "true"`. Default true. No LLM key needed.
- No external services required at import or runtime (SQLite + JSON files only). Network calls (web_search) must catch all exceptions.
- Every tool function returns a dict containing `"ok": bool` (plus data or `"error"`).
- Timestamps: UTC ISO strings via `db.now()`.

## Database (backend/database/db.py)
- `get_conn()` -> sqlite3.Connection: creates DATA_DIR, `row_factory=sqlite3.Row`, `PRAGMA foreign_keys=ON`.
- `init_db()` -> None: idempotent (`CREATE TABLE IF NOT EXISTS`), then seeds.
- `now()` -> str UTC ISO.
- Tables (exact columns):
  - users(id INTEGER PK, name TEXT, role TEXT, is_admin INTEGER DEFAULT 0, created_at TEXT)
  - teams(id INTEGER PK, name TEXT, created_at TEXT)
  - team_members(id INTEGER PK, team_id INTEGER, user_id INTEGER, role TEXT)
  - projects(id INTEGER PK, name TEXT UNIQUE, description TEXT, status TEXT DEFAULT 'active', completion_conditions TEXT /*JSON list*/, created_at TEXT, updated_at TEXT)
  - tasks(id INTEGER PK, project_id INTEGER, title TEXT, agent TEXT, deps TEXT /*JSON list of ids, default '[]'*/, state TEXT DEFAULT 'CREATED', attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 3, checkpoint TEXT /*JSON, default '{}'*/, result TEXT /*JSON*/, error TEXT, success_criteria TEXT DEFAULT '', steps TEXT /*JSON list, default '[]'*/, next_retry_at TEXT, created_at TEXT, updated_at TEXT)
  - agents(id INTEGER PK, name TEXT UNIQUE, kind TEXT, permission_level INTEGER, status TEXT DEFAULT 'idle')
  - agent_runs(id INTEGER PK, agent_name TEXT, task_id INTEGER, started_at TEXT, ended_at TEXT, ok INTEGER, output TEXT)
  - messages(id INTEGER PK, project_id INTEGER, role TEXT, content TEXT, created_at TEXT)
  - memories(id INTEGER PK, kind TEXT, key TEXT, value TEXT /*JSON*/, created_at TEXT, updated_at TEXT) + FTS5 table `memories_fts(key, value)` kept in sync via triggers on insert/update/delete; UNIQUE(kind, key).
  - documents(id INTEGER PK, project_id INTEGER, title TEXT, content TEXT, created_at TEXT)
  - tools(id INTEGER PK, name TEXT UNIQUE, permission_level INTEGER, description TEXT)
  - tool_permissions(id INTEGER PK, agent_name TEXT, tool_name TEXT, allowed INTEGER)
  - approvals(id INTEGER PK, kind TEXT, subject TEXT, detail TEXT /*JSON*/, state TEXT DEFAULT 'pending', requested_by TEXT, created_at TEXT, resolved_at TEXT, resolved_by TEXT)
  - activity_logs(id INTEGER PK, ts TEXT, agent TEXT, tool TEXT, args TEXT /*JSON*/, ok INTEGER, error TEXT)
  - push_tokens(id INTEGER PK, token TEXT UNIQUE, platform TEXT /*ios|android*/, created_at TEXT)
- Seed (INSERT OR IGNORE): owner account — name from env `ARTHUR_OWNER_NAME` (default `"owner"`), role `"Owner"`, `is_admin=1`; agents: manager/kind=manager/level 2, researcher/level 0, developer/level 1, browser/level 1, analyst/level 1, qa/level 1.
- `db.py` also exposes: `create_user(name, role="member", is_admin=False) -> int` and `get_admin_user() -> dict | None` (first user with is_admin=1).

## Task queue (backend/tasks/queue.py)
Dict shape for a task: `{id, project_id, title, agent, deps:list, state, attempts, max_attempts, checkpoint:dict, result:dict|None, error:str|None, success_criteria:str, steps:list, next_retry_at, created_at, updated_at}`.
States: CREATED, PLANNING, QUEUED, RUNNING, WAITING_FOR_TOOL, WAITING_FOR_APPROVAL, TESTING, FAILED, RETRYING, COMPLETED.
Functions:
- `create_project(name, description="", completion_conditions=None) -> int` (also in queue.py; updates memory profile)
- `create_task(project_id, title, agent, deps=None, success_criteria="", steps=None, max_attempts=3) -> int`
- `get_task(task_id) -> dict`
- `list_tasks(project_id=None, state=None) -> list[dict]`
- `list_projects() -> list[dict]`
- `claim_next() -> dict | None`: atomic (BEGIN IMMEDIATE): pick oldest task in (QUEUED, or RETRYING with next_retry_at <= now) whose deps are all COMPLETED; set RUNNING; return dict.
- `set_state(task_id, state, error=None, result=None)`
- `save_checkpoint(task_id, step_index:int, data:dict|None)` — merges into checkpoint JSON: `{"step_index": n, "data": {...}}`
- `retry_or_fail(task_id, error: str)`: attempts+=1; if attempts >= max_attempts: FAILED else RETRYING with next_retry_at = now + 5 * 2**attempts seconds.
- `requeue_with_fix(task_id, fix_note: str)`: attempts=0, append fix_note to checkpoint["fix_notes"], state=QUEUED.
- `recover_running()`: all RUNNING -> RETRYING (next_retry_at = now), called once at worker startup (crash recovery; resumes from checkpoint).

## Tools (backend/tools/)
`registry.py`:
- `class WaitingForApproval(Exception)`: attrs `approval_id`.
- `class ToolRegistry`: `register(name, fn, permission_level, description="")`; `call(agent, name, **kwargs)`: agent has `.name` and `.permission_level`; if `agent.permission_level < tool_level`: create approval (kind="tool_permission", subject=f"{agent.name} -> {name}", detail={agent, tool, args}) and raise WaitingForApproval; else run fn, append activity_logs row, return fn's dict; on exception log ok=0 and re-raise.
- `make_registry() -> ToolRegistry`: registers all built-ins below.
- Built-in tools + levels: `web_search`(0), `fetch_url`(0), `read_file`(0), `list_files`(0), `write_file`(1), `edit_file`(1), `run_shell`(1), `run_python`(1).
`web.py`: `web_search(query, max_results=5) -> {ok, results:[{title,url,snippet}]}` via DuckDuckGo html + requests, timeout 10, try/except -> {ok:False, error}. `fetch_url(url) -> {ok, text}` (strip tags crudely, first 4000 chars).
`files.py`: root jail = `DATA_DIR`. Helpers `_resolve(path)` — path may be absolute under DATA_DIR or relative; raise ValueError if escapes. `read_file(path)->{ok,content}`, `write_file(path, content)->{ok, path}`, `edit_file(path, old, new)->{ok, replacements}`, `list_files(path=".")-> {ok, files:[...]}`.
`terminal.py`: `run_shell(cmd, cwd=None, timeout=60) -> {ok, returncode, stdout, stderr}`; cwd defaults to DATA_DIR, must stay under ARTHUR_HOME; refuse patterns `rm -rf /`, `mkfs`, `:(){` -> {ok:False, error:"refused"}.
`python_tool.py`: `run_python(code, timeout=30) -> {ok, stdout, stderr, returncode}` via `sys.executable -c`.

## Security (backend/security/)
`permissions.py`: `LEVELS = {0: {"name":"READ",...}, 1: {"name":"LOW RISK",...}, 2: {"name":"EXTERNAL ACTIONS",...}, 3: {"name":"HIGH RISK",...}}` with spec descriptions; `can(agent_level, tool_level) -> bool` = `>=`; `describe(level)`.
Roles: `is_admin(user: dict) -> bool` = `bool(user.get("is_admin"))`. `can_resolve_approvals(user)` and `can_manage_users(user)` both = `is_admin(user)` (Owner/Admin only). Admin privilege NEVER bypasses the audit log or the approval queue: a level-3 tool action requested by any agent (including manager) still creates an approval request and is logged; the admin's power is to *resolve* that approval, not to skip it. Non-admin users cannot resolve approvals or manage users.
`approvals.py`: `create_approval(kind, subject, detail:dict, requested_by="") -> int`; `list_approvals(state="pending") -> list[dict]`; `resolve_approval(approval_id, approved:bool, resolved_by="")`; `get_approval(approval_id) -> dict`. `resolve_approval` raises `PermissionError` if `resolved_by` names a user for whom `is_admin` is False (look the user up by name; empty `resolved_by` in single-owner CLI context resolves to the admin owner).

## Memory (backend/memory/store.py)
- `remember(kind, key, value)` (value JSON-serializable; upsert by (kind,key)); `recall(kind, key) -> value|None`; `forget(kind, key)`; `search_memories(query, kind=None, limit=10) -> list[{kind,key,value}]` via FTS5 on memories_fts (fallback to LIKE if FTS missing).
- `get_project_profile(project_id) -> dict` (kind="project", key=f"profile:{project_id}", default {}); `update_project_profile(project_id, updates:dict)`.

## LLM (llm/client.py)
- `class LLMClient`: `__init__()` reads `DEMO_MODE`, `ARTHUR_LLM_BASE_URL`, `ARTHUR_LLM_API_KEY`, `ARTHUR_LLM_MODEL` (default "gpt-4o-mini").
- `chat(messages:[{role,content}], system=None) -> str`: if DEMO_MODE or no key -> `_demo_reply(messages)`; else POST `{base_url}/chat/completions` OpenAI-compatible, try/except -> fallback demo reply.
- `_demo_reply`: rule-based: if last user msg mentions "plan"/"tasks" -> short planning outline text; if "summar" -> first 200 chars + "…"; else generic acknowledgment. Deterministic.
- `summarize(text, max_chars=300) -> str` helper.

## Agents (backend/agents/)
`base.py`:
```python
class BaseAgent:
    def __init__(self, name, tools:list[str], permission_level:int, registry, llm): ...
    def call_tool(self, tool_name, **kwargs): return self.registry.call(self, tool_name, **kwargs)
    def run(self, task:dict) -> dict:  # -> {ok:bool, output:str, artifacts:list, error?:str}
```
`run` default: execute `task["steps"]` (list of `{tool, args}`) in order, skipping `step_index < checkpoint.step_index`; after each step call `save_checkpoint` (import from backend.tasks.queue — queue imports db only, so no cycle); collect outputs; return `{ok:True, output: summary, artifacts:[paths written]}`. On WaitingForApproval: re-raise. On other exception: return `{ok:False, error:str, output: partial}`.
- `researcher.py`: `ResearcherAgent(BaseAgent)` name="researcher", level 0. `run`: try `web_search(task["title"])` via registry; except -> note offline; then proceed with steps (manager provides a write_file research.md step); summarize findings into output.
- `developer.py`: `DeveloperAgent` name="developer", level 1. Uses default step execution.
- `qa.py`: `QAAgent` name="qa", level 1. Default step execution, then verify: if task["success_criteria"] and last step output lacks expected marker, return ok False. (Manager encodes markers in steps; QA just runs steps and reports.)
- `browser.py`, `analyst.py`: thin stubs subclassing BaseAgent, `run` returns `{ok:False, error:"Phase 8 (browser) / Phase 4 (analyst) — not implemented in MVP"}`. Docstring says so.

## Manager (backend/agents/manager.py)
- `class ManagerAgent`: `__init__(self, registry, llm)`, name="manager", permission_level=2.
- `handle_goal(goal_text, wait=True, timeout=600) -> str` (final report text):
  1. `init_db()`; create project (slug from goal); `update_project_profile`.
  2. `plan = self.plan_goal(goal_text)` -> `{"completion_conditions":[...], "tasks":[{title, agent, deps, success_criteria, steps}]}`; store conditions on project; create tasks QUEUED (deps as indices resolved to ids).
  3. Log plan to messages; print plan summary.
  4. If wait: poll every 1s until all tasks terminal (COMPLETED/FAILED) or timeout; run `monitor_tick()` each poll.
  5. `ok, unmet = self.verify_completion_conditions(project_id)`; build + return final report string.
- `plan_goal(goal)` DEMO_MODE: if "notes" in goal.lower() -> NOTES_CLI template (below); elif "resume" in goal.lower() -> generic scaffold plan; else generic scaffold plan. Non-demo: ask llm for JSON plan, fallback to generic.
- NOTES_CLI template: project dir `DATA_DIR/projects/tiny-markdown-notes-cli`. completion_conditions: ["research.md exists", "notes.py exists", "add/list commands work via smoke test", "README.md exists", "all tasks completed"]. Tasks:
  1. researcher "Research notes CLI design", steps: `[{"tool":"web_search","args":{"query":"tiny markdown notes CLI design best practices"}}]`, success_criteria "research summary in output".
  2. developer "Implement notes CLI", deps [1], steps: write `research.md` (canned design note below), write `notes.py` (TEMPLATE below), write `README.md`, run_shell `python -m py_compile notes.py` with cwd `projects/tiny-markdown-notes-cli` (relative to DATA_DIR). success_criteria "notes.py compiles".
  3. qa "Smoke test notes CLI", deps [2], steps: write `test_smoke.py` (TEMPLATE below), run_shell `python test_smoke.py` with cwd `projects/tiny-markdown-notes-cli` (relative to DATA_DIR). success_criteria "SMOKE OK".
  - NOTE: `write_file` paths are relative to the DATA_DIR jail, so pass `projects/tiny-markdown-notes-cli/notes.py` (NOT `data/projects/...`). Manager must pass paths relative to DATA_DIR.
  - PERMISSION RULE (contract bugfix): the manager MUST NEVER assign a step whose tool permission level exceeds the assigned agent's level (researcher=0: web_search/fetch_url/read_file/list_files only; developer/qa=1; manager=2). A level-0 agent given write_file would raise WaitingForApproval and stall the demo.
### research.md CANNED CONTENT (developer writes this file in the notes demo):
```markdown
# Notes CLI — research notes
Design: single-file Python CLI using argparse with subcommands `add <text>` and `list`.
Storage: append-only Markdown file (notes.md), one `- <text>` bullet per line.
Conventions: `--file` flag overrides the storage path; exit code 0 on success.
Test plan: add a note, list notes, assert the note appears in the output.
```
- `monitor_tick()`: for FAILED tasks: if checkpoint fix_notes < 2: analyze error (first 200 chars) -> `requeue_with_fix`; else create approval kind="task_failed". Report pending approvals count.
- `verify_completion_conditions(project_id)`: check each condition: "notes.py exists" -> file check; "add/list" -> qa task COMPLETED; "README" -> file check; "all tasks completed" -> states. Return (bool, unmet_list). Generic: all tasks COMPLETED.
- Final report format: header, goal, plan summary, per-task line (title: state, attempts), completion checklist [x]/[ ], project dir, "ARTHUR MVP demo complete."

### notes.py TEMPLATE (must be byte-correct, working):
```python
#!/usr/bin/env python3
"""Tiny markdown notes CLI (ARTHUR demo)."""
import argparse
import os
import sys

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.md")

def add_note(text, path):
    with open(path, "a", encoding="utf-8") as f:
        f.write("- " + text + "\n")

def list_notes(path):
    if not os.path.exists(path):
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:])
    return items

def main(argv=None):
    p = argparse.ArgumentParser(description="Tiny markdown notes CLI")
    p.add_argument("--file", default=DEFAULT_FILE, help="notes file")
    sub = p.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("add", help="add a note")
    pa.add_argument("text", help="note text")
    sub.add_parser("list", help="list notes")
    a = p.parse_args(argv)
    if a.cmd == "add":
        add_note(a.text, a.file)
        print("added")
    elif a.cmd == "list":
        for n in list_notes(a.file):
            print(n)

if __name__ == "__main__":
    main()
```
### test_smoke.py TEMPLATE:
```python
import os
import subprocess
import sys

d = os.path.dirname(os.path.abspath(__file__))
f = os.path.join(d, "notes.md")
if os.path.exists(f):
    os.remove(f)
r = subprocess.run([sys.executable, "notes.py", "add", "hello arthur"], cwd=d, capture_output=True, text=True)
assert r.returncode == 0, r.stderr
r = subprocess.run([sys.executable, "notes.py", "list"], cwd=d, capture_output=True, text=True)
assert r.returncode == 0 and "hello arthur" in r.stdout, r.stdout + r.stderr
print("SMOKE OK")
```

## Worker (backend/tasks/worker.py)
- `agent_factory(registry, llm) -> dict[str, BaseAgent]` building researcher/developer/qa (+stubs).
- `class Worker`: `__init__` builds registry/llm/agents; `start(stop_event=None)`: `recover_running()` once, then loop: `task = claim_next()`; if task: `self.run_task(task)` else `time.sleep(2)`.
- `run_task(task)`: log agent_runs start; `agent = self.agents[task["agent"]]`; try `res = agent.run(task)`; on `WaitingForApproval as e`: set_state WAITING_FOR_APPROVAL (store approval id in error field); on success dict: set COMPLETED + result; on `{ok:False}` or exception: `retry_or_fail`. Always write agent_runs end row.
- `if __name__ == "__main__"`: bootstrap sys.path, `Worker().start()` (blocking; Ctrl-C stops).

## Scheduler (backend/tasks/scheduler.py)
- `class Scheduler`: `schedule(name, interval_s, fn)`; `start()` spawns daemon thread per job looping `fn()` every interval_s (catch+print exceptions); `stop()` sets event.

## CLI (backend/main.py)
- Bootstrap sys.path; `init_db()`; banner "ARTHUR — Autonomous Reasoning & Task Handling Utility Runtime (MVP, DEMO_MODE=...)".
- FIRST-RUN OWNER SETUP: after `init_db()`, call `get_admin_user()`; if None, prompt: `No owner account found. Enter owner name [owner]: ` via `input()` (strip; default "owner"), then `create_user(name, role="Owner", is_admin=True)` and print confirmation "Owner '<name>' created with Admin privileges." This must run before the worker starts.
- Start `Worker` in daemon thread; `Scheduler` with `("manager_monitor", 10, manager.monitor_tick)`; `start()`.
- REPL `ARTHUR> `: `/projects` (list), `/tasks [project_id]` (list), `/agents` (list w/ status), `/approvals` (pending), `/approve <id>` (resolve approved), `/quit`. Any other text -> `print(manager.handle_goal(text))` (wait=True). Wrap in try/except KeyboardInterrupt.

## API (backend/api/server.py)
- `from fastapi import FastAPI; from fastapi.responses import FileResponse`; `app = FastAPI(title="ARTHUR")`; on startup `init_db()`.
- GET `/api/status` -> {online:true, demo_mode:bool, workers:1, current_user:{name, role, is_admin} (from `get_admin_user()`, null if none), counts:{projects,tasks by state, pending_approvals}}; `/api/projects`; `/api/tasks?project_id=`; `/api/agents`; `/api/approvals`; `/api/logs?limit=100`.
- POST `/api/chat` {message:str} -> if startswith "/": minimal command handling (/projects etc. as text); else `manager.handle_goal(message, wait=False)` -> {reply: plan_text, project_id}.
- POST `/api/approvals/{id}/resolve` {approved:bool} -> resolve.
- GET `/` -> FileResponse frontend/dashboard.html.
- Run: `uvicorn backend.api.server:app` from repo root.

## Frontend (frontend/dashboard.html)
Single file, dark futuristic. Sections: header with ARTHUR status dot AND a current-user chip showing `current_user.name` plus an "Admin" badge when `is_admin` (data from `/api/status`); projects; active agents; tasks w/ progress bar; queue counts; approvals w/ approve buttons; logs tail; chat box. JS `fetch` polls `/api/*` every 3s; chat POSTs `/api/chat`. No build step, no external CDN JS (inline only; CSS inline).

## Push notifications (backend)
- `backend/api/notify.py` (new file, owned by Builder E): `send_push(title: str, body: str, data: dict | None = None) -> None`. Reads all tokens from `push_tokens` table; POSTs to `https://exp.host/--/api/v2/push/send` with JSON `{"to": token, "title":..., "body":..., "data": data or {}}` via `requests` (timeout 10); wraps EVERYTHING in try/except (never raise — push failures must not break task execution). Imports only `backend.database.db` + `requests`.
- `backend/api/server.py` (Builder E): add `POST /api/push/register {token: str, platform: str}` → `INSERT OR IGNORE INTO push_tokens` → `{ok: true}`. Pydantic model for the body.
- Trigger points (fire-and-forget `send_push`, always inside try/except):
  - `backend/security/approvals.py` `create_approval` (Builder B): after insert → `send_push("ARTHUR: approval needed", subject, {"approval_id": id})`.
  - `backend/security/approvals.py` `resolve_approval` (Builder B): after resolve → `send_push("ARTHUR: approval " + ("approved" if approved else "denied"), subject, {"approval_id": id})`.
  - `backend/tasks/worker.py` `run_task` (Builder D): when a task lands in FAILED (after `retry_or_fail` yields FAILED) → `send_push("ARTHUR: task failed", task["title"], {"task_id": id, "project_id": pid})`. After marking COMPLETED: if ALL tasks of that project are in terminal states (COMPLETED/FAILED) → `send_push("ARTHUR: project completed", project_name, {"project_id": pid})`.
- `approvals.py`/`worker.py` import `send_push` lazily inside the trigger (function-level import) to avoid any import risk.

## Mobile app (mobile/)
Expo + React Native + TypeScript, one codebase for iOS + Android. All paths under `~/workspace/arthur-ai/mobile/`.
- `app.json`: name "ARTHUR", slug "arthur-ai", version "1.0.0", `ios.bundleIdentifier` + `android.package` = "com.arthur.ai".
- `package.json`: expo, react-native, expo-router, expo-notifications, expo-constants, react, react-native-safe-area-context, typescript, @types/react (scripts: start/test via expo/tsc).
- `tsconfig.json`: strict true, extends expo/tsconfig.base if present else standard strict config.
- `eas.json`: `cli.appVersionSource: "local"`, build profiles `development` (developmentClient), `preview`, `production`; submit configs for ios/android.
- `lib/api.ts`: `API_BASE = process.env.EXPO_PUBLIC_ARTHUR_API_URL ?? "http://localhost:8000"`; typed interfaces (Project, Task, AgentStatus, Approval, StatusResponse); wrappers: `getStatus(), sendChat(message), getProjects(), getTasks(projectId?), getAgents(), getApprovals(), resolveApproval(id, approved), getLogs(limit?), registerPushToken(token, platform)`. All `fetch` with JSON, throw on non-OK.
- `lib/notifications.ts`: `registerForPushNotifications(): Promise<string|null>` — request permissions via expo-notifications, get Expo push token, POST it via `registerPushToken(token, Platform.OS)`; returns token or null on failure/denial.
- `lib/theme.ts`: futuristic dark theme constants (colors, spacing, radius) matching the web dashboard aesthetic.
- Screens via Expo Router (`app/` dir): `_layout.tsx` (Stack + theme + notification registration on mount), `index.tsx` Chat (message list, input, POST /api/chat, polling not needed — append reply), `dashboard.tsx` (status dot, current-user chip + Admin badge, projects, agents, task progress bars; polls /api/* every 3s), `approvals.tsx` (pending approvals list with one-tap Approve/Deny → resolveApproval + refresh), `projects.tsx` + `projects/[id].tsx` (project + task detail).
- `.env.example`: `EXPO_PUBLIC_ARTHUR_API_URL=https://your-backend.example.com`.
- `mobile/README.md`: full publish guide — Apple Developer Program ($99/yr) + Google Play Console ($25 one-time) are the USER's own accounts; `eas build --platform all`; screenshots/metadata checklist; backend MUST be on a public HTTPS URL (document simple VPS + docker-compose deploy); OTA updates via `eas update`.
- Demo acceptance: `cd mobile && npx tsc --noEmit` passes; `npx expo start` boots Metro without errors (no phone needed).

## Packaging
- `requirements.txt`: fastapi, uvicorn, requests, pydantic.
- `.env.example`: DEMO_MODE=true, ARTHUR_HOME/ARTHUR_DB_PATH commented, ARTHUR_LLM_BASE_URL/API_KEY/MODEL commented.
- `docker-compose.yml`: services `api` (image python:3.11-slim, volume ./data, command: pip install -r requirements.txt && uvicorn backend.api.server:app --host 0.0.0.0 --port 8000), `worker` (same image, command: python backend/tasks/worker.py); postgres/redis/pgvector as COMMENTED profiles for Phase 5.
- `README.md`: vision, quickstart (DEMO_MODE demo: `DEMO_MODE=true python backend/main.py` then "build a tiny markdown notes CLI"), architecture diagram (ASCII), what's real vs stubbed, 11-phase roadmap, security notes (permission levels, approvals, jail, audit log).

## Sole-admin guarantee (HIGHEST PRIORITY — overrides any conflicting builder note)
1. Exactly one admin: the owner account. `init_db()`/`_seed()` create ONLY the
   owner (from `ARTHUR_OWNER_NAME`, default "owner") with `is_admin=1`. No
   built-in, default, backdoor, "system", "assistant", or agent admin accounts
   may exist. Agents live in the `agents` table, never in `users`.
2. `db.create_user(..., is_admin=True)` is honored ONLY when no admin exists
   yet (first-run bootstrap); otherwise it raises PermissionError. A second
   admin can never be created.
3. `db.update_user_role(user_id, role=..., is_admin=..., actor_name=...)`:
   the actor must be the existing admin (PermissionError otherwise); setting
   `is_admin=True` on anyone but the current sole admin raises
   PermissionError (no self-promotion, no second admin); demoting the sole
   admin raises PermissionError. Every change appends an `activity_logs` row
   with actor, timestamp, and old->new diff.
4. `permissions.require_admin_user(name)` is the central choke point for
   admin-gated actions. `permissions.set_tool_permission(...)` changes the
   `tool_permissions` table only for admin actors and audit-logs each change.
5. `approvals.resolve_approval` appends an `activity_logs` audit row
   (actor, timestamp, pending->approved/rejected diff) on every resolution.
6. ToolRegistry self-modification guardrail (`registry._self_modification_level`):
   - `write_file`/`edit_file` whose resolved path falls OUTSIDE
     `DATA_DIR/projects/` (the agent project workspace) -> LEVEL 3.
   - `run_shell`/`run_python` whose command/code matches auth-table SQL
     (`users`, `tool_permissions`, `push_tokens`), role-management helpers
     (`create_user`, `update_user_role`, `is_admin`, `resolve_approval`,
     ...), the arthur-ai source tree (`arthur-ai/(backend|mobile)/`,
     `backend/(database|security|tools|agents|api)/`), or secrets
     (`.env`, `ARTHUR_LLM_API_KEY`, `ARTHUR_OWNER`) -> LEVEL 3.
   - Level 3 can never be reached by any agent (max agent level is 2), so
     these calls ALWAYS create an owner approval and never execute
     autonomously — no auto-approve path. Approval detail carries
     `level_required: 3` and `guardrail: "self-modification"`.
   - The DATA_DIR jail (files.py) and ARTHUR_HOME shell jail remain as
     defense-in-depth behind this gate.
7. `backend/main.py` first-run owner prompt only fires when no admin exists;
   with `ARTHUR_OWNER_NAME` set, seeding covers it. The owner is always the
   sole admin; Muse is NOT an admin and has no privileged access built in.

## Security hardening + privacy (added 2026-09-29)
New modules under `backend/security/`:
- `secrets.py`: Fernet encrypt/decrypt (`encrypt_secret`/`decrypt_secret`),
  `store_secret`/`get_secret`/`delete_secret` backed by the `secrets` table,
  key from `ARTHUR_SECRET_KEY` or `$ARTHUR_HOME/.arthur_secret` (600).
  `scrub(text)`/`scrub_dict(d)` redact key-like values; `install_scrubbing()`
  attaches redaction to the root logger. Registry audit logging, approval
  detail, and manager chat-history writes all scrub before persisting.
- `auth.py`: bcrypt `hash_password`/`verify_password`/`set_user_password`;
  sessions table with SHA-256-hashed random tokens + expiry
  (`create_session`/`validate_session`/`revoke_session`,
  `ARTHUR_SESSION_HOURS` default 24); `login_attempts` table with
  `check_rate_limit` (5/min/IP), `lockout_until` (10 fails/15min -> 15min
  lock), `record_login_attempt`, `authenticate`.
- `egress.py`: `get_allowlist()` (`ARTHUR_EGRESS_ALLOWLIST`, default
  `html.duckduckgo.com,duckduckgo.com,exp.host,exponent.dev` + LLM host
  auto-added); `check_outbound(url, method)` default-DENY for non-GET to
  unknown hosts (`EgressBlocked`); wired into `notify.send_push` and
  `llm/client._remote_chat`. External-send tools must be LEVEL 2+.
- `data_rights.py`: `export_user_data(name)` (JSON dump; never includes
  `password_hash`); `delete_user_account(name, actor_name)` cascade-deletes
  sessions/login_attempts/team_members/activity/pending approvals/push
  tokens/user row; actor must be admin or self; NEVER the sole admin.
DB: `users.password_hash` added by `_migrate()`; new tables `sessions`,
`login_attempts`, `secrets`; `get_conn()` chmods the DB file 600.
API (`backend/api/server.py`): security-headers middleware (HSTS, CSP,
X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
Permissions-Policy); CORS from `ARTHUR_CORS_ORIGINS`; Pydantic models on all
bodies; `POST /api/auth/login` (rate-limited + lockout), `/api/auth/logout`,
`GET /api/auth/me`; `ARTHUR_REQUIRE_AUTH` (default on unless DEMO_MODE)
gates /api/* via Bearer session; approval resolve additionally requires
admin; `GET /api/user/export`, `DELETE /api/user`; `GET /privacy` serves
`PRIVACY_POLICY.md`. Public paths: `/`, `/privacy`, `/api/status`,
`/api/auth/*`, `/api/push/register`.
CLI (`backend/main.py`): owner password bootstrap (getpass or
`ARTHUR_OWNER_PASSWORD`); `/export` (writes 600-perm JSON to DATA_DIR);
`/delete-account` (typed DELETE confirmation; refuses sole admin).
Docs: root `PRIVACY_POLICY.md` (store-ready; placeholders [APP OPERATOR],
[CONTACT EMAIL], [LLM PROVIDER], [HOSTING PROVIDER], [HOSTING REGION]);
`mobile/README.md` section "Hosting your privacy policy" (backend `/privacy`
or GitHub Pages); `requirements.txt` adds `bcrypt`, `cryptography`.
Phase 9 note: Postgres row-level security (RLS) is the documented path for
team-mode data isolation.
