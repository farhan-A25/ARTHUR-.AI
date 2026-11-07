"""ARTHUR MVP — FastAPI HTTP server.

Endpoints (per CONTRACTS.md):
  GET  /api/status          -> online, demo_mode, current_user, counts
  GET  /api/projects
  GET  /api/tasks?project_id=
  GET  /api/agents
  GET  /api/approvals
  GET  /api/logs?limit=100
  POST /api/chat            -> {message} -> {reply[, project_id]}
  POST /api/approvals/{id}/resolve -> {approved: bool}  (admin only)
  POST /api/push/register   -> {token, platform}
  POST /api/auth/login      -> {name, password} -> {token, expires_at, user}
  POST /api/auth/logout     -> revoke current session
  GET  /api/auth/me         -> current session user
  GET  /api/user/export     -> JSON dump of all data about the user
  DELETE /api/user          -> cascade-delete the account (never the admin)
  GET  /privacy             -> the privacy policy (public, for store listings)
  GET  /                    -> dashboard.html

Security posture:
- Auth (bcrypt passwords, random expiring session tokens) is REQUIRED for
  /api/* whenever ARTHUR_REQUIRE_AUTH=true. Default: false in DEMO_MODE,
  true otherwise — production deployments get auth on by default.
- Login is rate-limited (5 attempts/min/IP) with lockout after 10 failures
  in 15 minutes.
- Security headers (HSTS, CSP, X-Content-Type-Options, ...) on every
  response; CORS restricted to ARTHUR_CORS_ORIGINS.
- All request bodies are Pydantic-validated. Secrets are scrubbed from
  anything logged or returned.

Run:  uvicorn backend.api.server:app --host 0.0.0.0 --port 8000   (from repo root)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import get as cfg

DEMO_MODE = os.environ.get("DEMO_MODE", str(cfg("demo_mode"))).lower() == "true"
REQUIRE_AUTH = (
    os.environ.get("ARTHUR_REQUIRE_AUTH", "false" if DEMO_MODE else "true").lower()
    == "true"
)
_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ARTHUR_CORS_ORIGINS", ",".join(cfg("cors_origins") or [])
    ).split(",")
    if o.strip()
]

# Paths that never require a session (health, login, public policy page,
# push registration from the mobile app).
_PUBLIC_PATHS = {
    "/", "/privacy", "/api/status",
    "/api/auth/login", "/api/auth/google", "/api/auth/logout", "/api/push/register",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.database.db import init_db
    from backend.security.secrets import install_scrubbing

    install_scrubbing()
    init_db()
    yield


app = FastAPI(title="ARTHUR", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
            " img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

_manager = None


def _load_llm_client():
    try:
        from backend.llm.client import LLMClient
    except ImportError:
        from llm.client import LLMClient  # noqa: F401
    return LLMClient


def get_manager():
    """Lazily build the singleton ManagerAgent (registry + LLM, no network)."""
    global _manager
    if _manager is None:
        from backend.tools.registry import make_registry
        from backend.agents.manager import ManagerAgent
        LLMClient = _load_llm_client()
        _manager = ManagerAgent(make_registry(), LLMClient())
    return _manager


# ----------------------------------------------------------------------------
# Auth helpers
# ----------------------------------------------------------------------------
def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def get_current_user(request: Request) -> dict:
    """Dependency: the session user, or 401 when auth is required.

    A presented bearer token is ALWAYS validated — even when auth is not
    required — so revoked/expired tokens can never silently keep working.
    Without any token and with auth disabled (DEMO_MODE), act as the owner.
    """
    from backend.security.auth import validate_session

    token = _bearer_token(request)
    user = validate_session(token) if token else None
    if user is None:
        if token:
            # A credential was presented but is invalid, expired, or revoked.
            raise HTTPException(
                status_code=401, detail="invalid or expired session"
            )
        if REQUIRE_AUTH:
            raise HTTPException(status_code=401, detail="authentication required")
        # DEMO_MODE / auth disabled: act as the owner (single-user local).
        from backend.database.db import get_admin_user

        owner = get_admin_user()
        user = {
            "id": owner["id"] if owner else 0,
            "name": owner["name"] if owner else "owner",
            "role": owner["role"] if owner else "Owner",
            "is_admin": True,
        }
    return user


def require_admin(request: Request) -> dict:
    """Dependency: current user must be an admin (sole-admin guarantee)."""
    user = get_current_user(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _handle_slash_command(message: str) -> str:
    """Minimal text replies for '/'-prefixed chat input."""
    from backend.tasks.queue import list_projects, list_tasks
    from backend.security.approvals import list_approvals
    from backend.database.db import get_conn

    cmd = message.strip()
    if cmd == "/projects":
        projects = list_projects()
        if not projects:
            return "(no projects yet)"
        return "\n".join(f"[{p['id']}] {p['name']} ({p['status']})" for p in projects)
    if cmd.startswith("/tasks"):
        parts = cmd.split()
        pid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        tasks = list_tasks(project_id=pid)
        if not tasks:
            return "(no tasks)"
        return "\n".join(f"[{t['id']}] {t['title']} — {t['agent']} — {t['state']}" for t in tasks)
    if cmd == "/agents":
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT name, kind, permission_level, status FROM agents ORDER BY name").fetchall()
        finally:
            conn.close()
        return "\n".join(
            f"{r['name']} ({r['kind']}, level {r['permission_level']}) — {r['status']}" for r in rows)
    if cmd == "/approvals":
        pending = list_approvals()
        if not pending:
            return "(no pending approvals)"
        return "\n".join(
            f"[{a['id']}] {a['kind']}: {a['subject']} (by {a['requested_by']})" for a in pending)
    return "Unknown command. Try /projects, /tasks, /agents, /approvals."


# ----------------------------------------------------------------------------
# Request models (Pydantic input validation)
# ----------------------------------------------------------------------------
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


class ResolveIn(BaseModel):
    approved: bool = False


class LoginIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class GoogleIn(BaseModel):
    id_token: str = Field(min_length=1, max_length=8192)


class PushRegister(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    platform: str = Field(default="", max_length=64)


class DeleteUserIn(BaseModel):
    name: str | None = Field(default=None, max_length=128)


# ----------------------------------------------------------------------------
# Public endpoints
# ----------------------------------------------------------------------------
@app.get("/api/status")
def api_status():
    from backend.database.db import get_admin_user, get_conn
    from backend.security.approvals import list_approvals
    from backend.tasks.queue import list_projects

    owner = get_admin_user()
    conn = get_conn()
    try:
        task_states = {}
        for row in conn.execute("SELECT state, COUNT(*) AS n FROM tasks GROUP BY state"):
            task_states[row["state"]] = row["n"]
    finally:
        conn.close()
    return {
        "online": True,
        "demo_mode": DEMO_MODE,
        "auth_required": REQUIRE_AUTH,
        "workers": 1,
        "current_user": ({
            "name": owner["name"],
            "role": owner["role"],
            "is_admin": bool(owner["is_admin"]),
        } if owner else None),
        "counts": {
            "projects": len(list_projects()),
            "tasks": task_states,
            "pending_approvals": len(list_approvals()),
        },
    }


@app.post("/api/auth/login")
def api_login(body: LoginIn, request: Request):
    from backend.security import auth

    ip = request.client.host if request.client else ""
    if not auth.check_rate_limit(ip):
        raise HTTPException(
            status_code=429, detail="too many login attempts; try again later")
    locked_until = auth.lockout_until(ip, body.name.strip())
    if locked_until:
        raise HTTPException(
            status_code=403,
            detail="account temporarily locked; try again later")
    user = auth.authenticate(body.name.strip(), body.password)
    auth.record_login_attempt(ip, body.name.strip(), bool(user))
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    token, expires_at = auth.create_session(user["id"])
    return {
        "token": token,
        "expires_at": expires_at,
        "user": {
            "name": user["name"],
            "role": user["role"],
            "is_admin": bool(user["is_admin"]),
        },
    }


@app.post("/api/auth/logout")
def api_logout(request: Request):
    from backend.security.auth import revoke_session

    revoke_session(_bearer_token(request))
    return {"ok": True}


def _google_name_matches(user_name: str, google_name: str, email: str) -> bool:
    """Fuzzy owner matching: exact name, or a long name-token inside the
    Gmail address (e.g. user 'Mohammed Farhan' vs farhan25s@gmail.com)."""
    un, gn = user_name.strip().lower(), google_name.strip().lower()
    if un and un == gn:
        return True
    local = email.split("@")[0].lower()
    for token in un.split():
        if len(token) >= 3 and token in local:
            return True
    return False


@app.post("/api/auth/google")
def api_google_login(body: GoogleIn):
    """Exchange a Google ID token for an ARTHUR session.

    The token is verified with Google; the audience must be one of the
    ARTHUR_GOOGLE_CLIENT_IDS (comma-separated) when that env var is set.
    The Google identity is matched to an existing ARTHUR user — on a fresh
    server with no users yet, the first Google sign-in provisions the owner.
    """
    import json
    import urllib.parse
    import urllib.request

    from backend.database.db import get_conn, now
    from backend.security import auth

    try:
        url = "https://oauth2.googleapis.com/tokeninfo?id_token=" + urllib.parse.quote(
            body.id_token
        )
        req = urllib.request.Request(url, headers={"User-Agent": "ARTHUR/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            info = json.loads(r.read().decode())
    except Exception:
        raise HTTPException(status_code=401, detail="invalid Google token")
    if info.get("email_verified") != "true":
        raise HTTPException(status_code=401, detail="Google email not verified")
    allowed = [
        c.strip()
        for c in os.environ.get("ARTHUR_GOOGLE_CLIENT_IDS", "").split(",")
        if c.strip()
    ]
    if allowed and info.get("aud") not in allowed:
        raise HTTPException(status_code=401, detail="Google token not for this app")

    email = str(info.get("email", "")).strip()
    google_name = str(info.get("name", "")).strip() or email.split("@")[0]
    if not email:
        raise HTTPException(status_code=401, detail="Google did not share an email")

    conn = get_conn()
    try:
        rows = conn.execute("SELECT id, name, role, is_admin FROM users").fetchall()
        user = None
        for row in rows:
            if _google_name_matches(row["name"] or "", google_name, email):
                user = dict(row)
                break
        if user is None:
            if rows:
                raise HTTPException(
                    status_code=403,
                    detail="this Google account is not linked to an ARTHUR user",
                )
            # Fresh server: first Google sign-in becomes the owner.
            cur = conn.execute(
                "INSERT INTO users(name, role, is_admin, created_at) VALUES (?, 'Owner', 1, ?)",
                (google_name, now()),
            )
            conn.commit()
            user = {
                "id": cur.lastrowid,
                "name": google_name,
                "role": "Owner",
                "is_admin": 1,
            }
    finally:
        conn.close()

    token, expires_at = auth.create_session(user["id"])
    return {
        "token": token,
        "expires_at": expires_at,
        "user": {
            "name": user["name"],
            "role": user["role"],
            "is_admin": bool(user["is_admin"]),
        },
    }


@app.get("/api/auth/me")
def api_me(user: dict = Depends(get_current_user)):
    return {
        "name": user["name"],
        "role": user["role"],
        "is_admin": bool(user["is_admin"]),
    }


@app.get("/privacy")
def privacy():
    path = os.path.join(ROOT, "PRIVACY_POLICY.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="privacy policy not found")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8")


# ----------------------------------------------------------------------------
# Authenticated endpoints
# ----------------------------------------------------------------------------
@app.get("/api/projects")
def api_projects(user: dict = Depends(get_current_user)):
    from backend.tasks.queue import list_projects
    return list_projects()


@app.get("/api/tasks")
def api_tasks(project_id: int | None = None, user: dict = Depends(get_current_user)):
    from backend.tasks.queue import list_tasks
    return list_tasks(project_id=project_id)


@app.get("/api/agents")
def api_agents(user: dict = Depends(get_current_user)):
    from backend.database.db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, kind, permission_level, status FROM agents ORDER BY name").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/approvals")
def api_approvals(user: dict = Depends(get_current_user)):
    from backend.security.approvals import list_approvals
    return list_approvals()


@app.get("/api/logs")
def api_logs(limit: int = 100, user: dict = Depends(get_current_user)):
    from backend.database.db import get_conn
    limit = max(1, min(limit, 1000))
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, ts, agent, tool, args, ok, error FROM activity_logs "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.post("/api/chat")
def api_chat(body: ChatIn, user: dict = Depends(get_current_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    if message.startswith("/"):
        return {"reply": _handle_slash_command(message)}
    manager = get_manager()
    from backend.tasks.queue import list_projects
    before = {p["id"] for p in list_projects()}
    reply = manager.handle_goal(message, wait=False)
    after = list_projects()
    new_ids = [p["id"] for p in after if p["id"] not in before]
    project_id = new_ids[0] if new_ids else (after[-1]["id"] if after else None)
    return {"reply": reply, "project_id": project_id}


@app.post("/api/approvals/{approval_id}/resolve")
def api_resolve_approval(
    approval_id: int, body: ResolveIn, admin: dict = Depends(require_admin)
):
    from backend.security.approvals import resolve_approval, get_approval

    try:
        resolve_approval(approval_id, bool(body.approved),
                         resolved_by=admin["name"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "approval": get_approval(approval_id)}


@app.post("/api/push/register")
def api_push_register(body: PushRegister):
    from backend.database.db import get_conn, now
    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO push_tokens (token, platform, created_at)"
            " VALUES (?, ?, ?)",
            (token, body.platform or "", now()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Data rights: export + deletion
# ----------------------------------------------------------------------------
@app.get("/api/user/export")
def api_export(user: dict = Depends(get_current_user)):
    from backend.security.data_rights import export_user_data

    try:
        return export_user_data(user["name"])
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/user")
def api_delete_user(
    body: DeleteUserIn | None = None, admin: dict = Depends(get_current_user)
):
    from backend.security.data_rights import delete_user_account

    target = (body.name if body and body.name else admin["name"]).strip()
    try:
        return delete_user_account(target, actor_name=admin["name"])
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/")
def index():
    return FileResponse(os.path.join(ROOT, "frontend", "dashboard.html"))


# The ARTHUR mobile app, exported for web — served as a static SPA at /app
# so one URL delivers the entire app: open it and it just runs.
try:
    from fastapi.staticfiles import StaticFiles

    _WEB_DIR = os.path.join(ROOT, "web")
    if os.path.isdir(_WEB_DIR):
        app.mount("/app", StaticFiles(directory=_WEB_DIR, html=True), name="arthur-app")
except Exception:
    pass
