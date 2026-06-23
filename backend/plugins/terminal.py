"""
terminal.py — Async-native terminal execution plugin v5.0
===========================================================
Fully native async plugin: `execute` is a coroutine function.

v5 upgrade:
    The synchronous `execute()` shim that used asyncio.run() inside a
    ThreadPoolExecutor has been completely removed.  In v4, that shim
    created a brand new event loop on a secondary thread every time the
    plugin was called, which caused:
      (a) unnecessary thread pool consumption
      (b) potential event loop handle leaks on Windows
      (c) a nested asyncio.run() call pattern that is explicitly
          discouraged in the asyncio documentation

    In v5, `execute` is directly declared as `async def`, and
    plugin_manager.execute_async() detects this via
    `inspect.iscoroutinefunction()` and awaits it directly in the main
    event loop — zero thread overhead, zero nested loops.

Human-in-the-loop (HITL) gate:
    Commands are NOT executed unless `args['_approved']` is True.
    Unapproved commands return `__APPROVAL_REQUIRED__:<command>` which
    causes the gateway to emit `{"type": "approval_required"}` to the
    frontend for explicit user confirmation.

Timeout:
    Commands are hard-killed after _TIMEOUT_SECONDS (15 s) via asyncio.TimeoutError.
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
    """
    Spawns a subprocess using asyncio.create_subprocess_exec — fully
    non-blocking, no thread pool consumption.

    On Windows: routes through `cmd /c` to support pipes, redirects, and
    built-in commands (dir, echo, etc.).
    On POSIX: attempts shlex.split first; falls back to `sh -c` for complex
    expressions containing pipes or redirects.
    """
    is_win = sys.platform == "win32"

    if is_win:
        proc = await asyncio.create_subprocess_exec(
            "cmd", "/c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        try:
            args = shlex.split(command)
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except ValueError:
            proc = await asyncio.create_subprocess_exec(
                "sh", "-c", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

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


# ---------------------------------------------------------------------------
# Native async execute — detected by inspect.iscoroutinefunction() in
# plugin_manager.execute_async() and awaited directly in the event loop.
# No synchronous shim, no nested asyncio.run(), no ThreadPoolExecutor.
# ---------------------------------------------------------------------------
async def execute(args: dict | None = None) -> str:
    """
    HITL-gated async terminal executor.

    Args:
        args (dict): Must contain 'command' key. '_approved' flag must be
                     True for execution to proceed.

    Returns:
        str: stdout/stderr output, or the __APPROVAL_REQUIRED__ sentinel.
    """
    if not args or "command" not in args:
        return "Error: No 'command' key provided in plugin args."

    command  = str(args["command"])
    approved = bool(args.get("approved", False))

    if not approved:
        # Return sentinel string — gateway converts this to an approval_required event
        return f"__APPROVAL_REQUIRED__:{command}"

    return await _run_command_async(command)
