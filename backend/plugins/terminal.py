"""
terminal.py — Async-native terminal execution plugin v5.0
===========================================================
Fully native async plugin: `execute` is a coroutine function.
"""
from __future__ import annotations

import asyncio
import shlex
import sys
from typing import Any

PLUGIN_METADATA: dict[str, Any] = {
    "name":        "terminal",
    "description": "Executes shell commands on the local OS via a non-blocking async subprocess.",
    "keywords":    ["run", "execute", "command", "shell", "terminal", "cmd", "powershell"],
}

_TIMEOUT_SECONDS: int = 15


async def _run_command_async(command: str) -> str:
    if not command:
        return "Error: Empty command."

    try:
        # Run using powershell to support builtins like echo and $env variables
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        return f"Error executing command: {e}"

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return f"Error: Command timed out after {_TIMEOUT_SECONDS}s."

    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    
    MAX_LEN = 10000
    if len(out) > MAX_LEN:
        out = out[:MAX_LEN] + "\n...[TRUNCATED]"
    if len(err) > MAX_LEN:
        err = err[:MAX_LEN] + "\n...[TRUNCATED]"

    if err:
        out += f"\nSTDERR:\n{err}"
    return out or "Command executed successfully with no output."


async def execute(args: dict | None = None) -> str:
    if not args or "command" not in args:
        return "Error: No 'command' key provided in plugin args."

    command  = str(args["command"])
    approved = bool(args.get("_approved", args.get("approved", False)))

    if not approved:
        return f"__APPROVAL_REQUIRED__:{command}"

    return await _run_command_async(command)
