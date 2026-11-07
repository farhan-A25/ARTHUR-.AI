#!/usr/bin/env python3
"""ARTHUR auth API smoke test (stdlib + requests only).

Spins up the real FastAPI server against a throwaway SQLite DB and
exercises the full session lifecycle:

  1. protected endpoint without token      -> 401
  2. login with wrong password             -> 401/403 detail
  3. login with correct password           -> token + expiry + user
  4. GET /api/auth/me with bearer token    -> owner user
  5. protected endpoint with bearer token  -> 200
  6. protected endpoint with bad token      -> 401
  7. logout                                -> ok
  8. token reuse after logout              -> 401

Usage:  python3 tests/test_auth_api.py
Exit code 0 = all checks passed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

import requests

BASE = "http://127.0.0.1:18098"
OWNER = "Test Owner"
PASSWORD = "CorrectHorse!123"


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        check.failed += 1


check.failed = 0  # type: ignore[attr-defined]


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="arthur-auth-test-")
    db_path = os.path.join(tmp, "test.db")
    env = {
        **os.environ,
        "DEMO_MODE": "false",
        "ARTHUR_AUTH_REQUIRED": "true",
        "ARTHUR_DB_PATH": db_path,
        "ARTHUR_OWNER_NAME": OWNER,
    }
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_python = os.path.join(root, ".venv", "bin", "python")
    python = venv_python if os.path.exists(venv_python) else sys.executable

    server = subprocess.Popen(
        [python, "-m", "uvicorn", "backend.api.server:app",
         "--host", "127.0.0.1", "--port", "18098"],
        cwd=root, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(60):
            try:
                requests.get(f"{BASE}/api/status", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            print("[FAIL] server did not start")
            return 1

        # Seed the owner password directly (same as first-run CLI would).
        seed = subprocess.run(
            [python, "-c",
             "from backend.database.db import get_user_by_name;"
             "from backend.security.auth import set_user_password;"
             f"u = get_user_by_name({OWNER!r});"
             f"set_user_password(u['id'], {PASSWORD!r})"],
            cwd=root, env=env, capture_output=True, text=True,
        )
        check("seed owner password", seed.returncode == 0, seed.stderr[-200:])

        # 1. No token -> 401 on protected route.
        r = requests.get(f"{BASE}/api/projects", timeout=5)
        check("protected route without token -> 401", r.status_code == 401,
              f"got {r.status_code}")

        # 2. Wrong password rejected.
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"name": OWNER, "password": "nope"}, timeout=5)
        check("login with wrong password rejected",
              r.status_code in (401, 403), f"got {r.status_code}")

        # 3. Correct login.
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"name": OWNER, "password": PASSWORD}, timeout=5)
        ok = r.status_code == 200
        body = r.json() if ok else {}
        token = body.get("token", "")
        check("login returns token + expiry + user",
              ok and len(token) > 20 and body.get("expires_at")
              and body.get("user", {}).get("name") == OWNER,
              f"got {r.status_code}")
        headers = {"Authorization": f"Bearer {token}"}

        # 4. /api/auth/me
        r = requests.get(f"{BASE}/api/auth/me", headers=headers, timeout=5)
        check("/api/auth/me returns owner",
              r.status_code == 200 and r.json().get("is_admin") is True,
              f"got {r.status_code}")

        # 5. Protected route with token.
        r = requests.get(f"{BASE}/api/projects", headers=headers, timeout=5)
        check("protected route with token -> 200", r.status_code == 200,
              f"got {r.status_code}")

        # 6. Bad token.
        r = requests.get(f"{BASE}/api/projects",
                         headers={"Authorization": "Bearer badtoken"}, timeout=5)
        check("bad token -> 401", r.status_code == 401,
              f"got {r.status_code}")

        # 7. Logout.
        r = requests.post(f"{BASE}/api/auth/logout", headers=headers, timeout=5)
        check("logout ok", r.status_code == 200 and r.json().get("ok") is True,
              f"got {r.status_code}")

        # 8. Token dead after logout.
        r = requests.get(f"{BASE}/api/projects", headers=headers, timeout=5)
        check("token rejected after logout -> 401", r.status_code == 401,
              f"got {r.status_code}")

        print(f"\n{8 - check.failed}/8 checks passed")
        return 1 if check.failed else 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()


if __name__ == "__main__":
    sys.exit(main())
