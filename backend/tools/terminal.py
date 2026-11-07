"""Shell tool: guarded, jailed command execution.

- cwd defaults to DATA_DIR and must stay under ARTHUR_HOME.
- Dangerous patterns are refused outright: "rm -rf /", "mkfs", ":(){".
"""
from __future__ import annotations

import os
import subprocess

from backend.database.db import ARTHUR_HOME, DATA_DIR

_REFUSED_PATTERNS = ("rm -rf /", "mkfs", ":(){")


def run_shell(cmd, cwd=None, timeout=60):
    """Run ``cmd`` in a shell.

    Returns {ok, returncode, stdout, stderr} where ok = (returncode == 0).
    Refused commands return {ok: False, error: "refused"}.
    """
    for pattern in _REFUSED_PATTERNS:
        if pattern in cmd:
            return {"ok": False, "error": "refused"}

    home = os.path.realpath(ARTHUR_HOME)
    if cwd:
        # Relative cwd is resolved against DATA_DIR (the files jail root),
        # matching files.py; absolute cwd must still stay under ARTHUR_HOME.
        if not os.path.isabs(cwd):
            cwd = os.path.join(DATA_DIR, cwd)
        target = os.path.realpath(cwd)
    else:
        target = os.path.realpath(DATA_DIR)
    try:
        inside = os.path.commonpath([home, target]) == home
    except ValueError:
        inside = False
    if not inside:
        return {"ok": False, "error": "cwd escapes ARTHUR_HOME"}

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=target,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "timeout after %ss" % (timeout,),
            "returncode": -1,
            "stdout": "",
            "stderr": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "returncode": -1,
            "stdout": "",
            "stderr": "",
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
