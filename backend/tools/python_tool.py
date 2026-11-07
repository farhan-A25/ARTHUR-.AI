"""Python tool: run code via sys.executable -c, capturing output."""
from __future__ import annotations

import subprocess
import sys


def run_python(code, timeout=30):
    """Execute ``code`` with the current Python interpreter.

    Returns {ok, stdout, stderr, returncode} where ok = (returncode == 0).
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "timeout after %ss" % (timeout,),
            "stdout": "",
            "stderr": "",
            "returncode": -1,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "stdout": "",
            "stderr": "",
            "returncode": -1,
        }
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
    }
