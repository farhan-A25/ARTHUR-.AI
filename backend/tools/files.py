"""File tools jailed to DATA_DIR.

Every path is resolved against DATA_DIR and rejected with ValueError if it
escapes the jail. All functions return dicts containing "ok".
"""
from __future__ import annotations

import os

from backend.database.db import DATA_DIR


def _resolve(path):
    """Resolve ``path`` (absolute or relative) inside DATA_DIR.

    Raises ValueError if the resolved path escapes DATA_DIR.
    """
    root = os.path.realpath(DATA_DIR)
    if os.path.isabs(path):
        resolved = os.path.realpath(path)
    else:
        resolved = os.path.realpath(os.path.join(root, path))
    if os.path.commonpath([root, resolved]) != root:
        raise ValueError("path escapes DATA_DIR: %r" % (path,))
    return resolved


def read_file(path):
    """Read a text file. -> {ok, path, content}."""
    try:
        full = _resolve(path)
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
        return {"ok": True, "path": path, "content": content}
    except ValueError:
        raise
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def write_file(path, content):
    """Write ``content`` to a file (creating parent dirs). -> {ok, path}."""
    try:
        full = _resolve(path)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": path}
    except ValueError:
        raise
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def edit_file(path, old, new):
    """Replace ``old`` with ``new`` in a file. -> {ok, path, replacements}."""
    try:
        full = _resolve(path)
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
        replacements = content.count(old)
        if replacements:
            with open(full, "w", encoding="utf-8") as f:
                f.write(content.replace(old, new))
        return {"ok": True, "path": path, "replacements": replacements}
    except ValueError:
        raise
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def list_files(path="."):
    """List entries under ``path`` (relative to DATA_DIR). -> {ok, files}."""
    try:
        full = _resolve(path)
        entries = []
        for name in sorted(os.listdir(full)):
            entry_path = os.path.join(full, name)
            entries.append(
                {
                    "name": name,
                    "is_dir": os.path.isdir(entry_path),
                    "size": os.path.getsize(entry_path),
                }
            )
        return {"ok": True, "path": path, "files": entries}
    except ValueError:
        raise
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
