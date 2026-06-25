"""
file_system.py — Async-native file I/O plugin.
All disk operations run through asyncio.to_thread to avoid blocking the event loop.
"""
from __future__ import annotations

import asyncio
import fnmatch
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

PLUGIN_METADATA: dict[str, Any] = {
    "name": "file_system",
    "description": (
        "Reads, writes, appends, deletes, lists, and searches files and directories "
        "on the local workspace without blocking the async event loop."
    ),
    "keywords": [
        "read", "write", "file", "save", "load", "workspace",
        "append", "delete", "list", "directory", "folder", "search", "find",
    ],
}

# ---------------------------------------------------------------------------
# Blocking I/O helpers — each wrapped in asyncio.to_thread at call-site
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent

def _enforce_sandbox(filepath: str) -> Path:
    p = Path(filepath).resolve()
    if not p.is_relative_to(WORKSPACE_ROOT):
        raise PermissionError(f"Access denied: '{filepath}' is outside the workspace sandbox.")
    return p
def _read(filepath: str) -> str:
    p = _enforce_sandbox(filepath)
    if not p.exists():
        return f"Error: '{filepath}' does not exist."
    if not p.is_file():
        return f"Error: '{filepath}' is not a regular file."
    content = p.read_text(encoding="utf-8", errors="replace")
    size_kb = round(p.stat().st_size / 1024, 2)
    return f"[{filepath}] ({size_kb} KB)\n{content}"


def _write(filepath: str, content: str, mode: str = "w") -> str:
    p = _enforce_sandbox(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open(mode, encoding="utf-8") as f:
        f.write(content)
    verb = "Appended to" if mode == "a" else "Wrote"
    return f"{verb} '{filepath}' successfully ({len(content)} chars)."


def _delete(filepath: str) -> str:
    p = _enforce_sandbox(filepath)
    if not p.exists():
        return f"Error: '{filepath}' does not exist."
    if p.is_file():
        p.unlink()
        return f"Deleted file '{filepath}'."
    # Recursively remove directory
    import shutil
    shutil.rmtree(p)
    return f"Deleted directory '{filepath}' and all contents."


def _list_dir(dirpath: str, pattern: str = "*") -> str:
    p = _enforce_sandbox(dirpath)
    if not p.exists():
        return f"Error: '{dirpath}' does not exist."
    if not p.is_dir():
        return f"Error: '{dirpath}' is not a directory."
    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines: list[str] = []
    for e in entries:
        if not fnmatch.fnmatch(e.name, pattern):
            continue
        try:
            st   = e.stat()
            mod  = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            kind = "DIR " if e.is_dir() else "FILE"
            size = f"{round(st.st_size/1024,1):>8} KB" if e.is_file() else "         -"
            lines.append(f"{kind}  {mod}  {size}  {e.name}")
        except PermissionError:
            lines.append(f"????  [permission denied]  {e.name}")
    header = f"Directory listing: {dirpath}  ({len(lines)} items)\n"
    return header + "\n".join(lines) if lines else header + "(empty)"


def _search(dirpath: str, pattern: str, max_results: int = 40) -> str:
    p = _enforce_sandbox(dirpath)
    if not p.exists():
        return f"Error: '{dirpath}' does not exist."
    found: list[str] = []
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                found.append(str(Path(root) / name))
            if len(found) >= max_results:
                break
        if len(found) >= max_results:
            break
    if not found:
        return f"No files matching '{pattern}' found under '{dirpath}'."
    result = "\n".join(found)
    truncated = "" if len(found) < max_results else f"\n... (first {max_results} results shown)"
    return f"Found {len(found)} file(s):\n{result}{truncated}"


def _info(filepath: str) -> str:
    p = _enforce_sandbox(filepath)
    if not p.exists():
        return f"Error: '{filepath}' does not exist."
    st = p.stat()
    return (
        f"Path:     {p.resolve()}\n"
        f"Type:     {'Directory' if p.is_dir() else 'File'}\n"
        f"Size:     {round(st.st_size / 1024, 2)} KB\n"
        f"Created:  {datetime.fromtimestamp(st.st_ctime)}\n"
        f"Modified: {datetime.fromtimestamp(st.st_mtime)}\n"
        f"Mode:     {stat.filemode(st.st_mode)}"
    )


# ---------------------------------------------------------------------------
# Async execute entrypoint
# ---------------------------------------------------------------------------
_ACTION_MAP = {
    "read":    lambda a: _read(a["filepath"]),
    "write":   lambda a: _write(a["filepath"], a.get("content", ""), "w"),
    "append":  lambda a: _write(a["filepath"], a.get("content", ""), "a"),
    "delete":  lambda a: _delete(a["filepath"]),
    "list":    lambda a: _list_dir(a.get("filepath", "."), a.get("pattern", "*")),
    "search":  lambda a: _search(
        a.get("filepath", "."), a.get("pattern", "*"),
        int(a.get("max_results", 40))
    ),
    "info":    lambda a: _info(a["filepath"]),
}


async def execute(args: dict | None = None) -> str:
    if not args:
        return "Error: No arguments provided."
    action = args.get("action", "").strip().lower()
    if action not in _ACTION_MAP:
        supported = ", ".join(_ACTION_MAP.keys())
        return f"Error: Unknown action '{action}'. Supported: {supported}."
    # Validate required 'filepath' for non-list actions
    if action not in ("list",) and not args.get("filepath"):
        return "Error: 'filepath' is required."
    try:
        return await asyncio.to_thread(_ACTION_MAP[action], args)
    except PermissionError as exc:
        return f"Permission denied: {exc}"
    except Exception as exc:
        return f"Error performing file operation '{action}': {exc}"
