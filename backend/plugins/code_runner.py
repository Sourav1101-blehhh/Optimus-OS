import subprocess
import tempfile
import os
import sys

PLUGIN_METADATA = {
    "name": "code_runner",
    "description": (
        "Writes a Python script to a temporary file, executes it, and returns the output. "
        "Use this to run any custom code the user requests."
    ),
    "keywords": ["code", "run", "execute", "python", "script", "calculate", "compute", "program"],
}

# ---------------------------------------------------------------------------
# AST Static Analysis Gate
# ---------------------------------------------------------------------------
import ast

_BLOCKED_MODULES   = {"os", "subprocess", "shutil", "socket", "ctypes", "sys"}
_BLOCKED_BUILTINS  = {"exec", "eval", "compile", "__import__"}

def _static_scan(code: str) -> list[str]:
    """Returns list of violation strings, empty if clean."""
    violations = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        violations.append(f"SyntaxError: {e}")
        return violations
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in node.names]
            for n in names:
                if n in _BLOCKED_MODULES:
                    violations.append(f"Blocked import: '{n}'")
        elif isinstance(node, ast.Call):
            func = node.func
            name = (func.id if isinstance(func, ast.Name) else
                    func.attr if isinstance(func, ast.Attribute) else None)
            if name in _BLOCKED_BUILTINS:
                violations.append(f"Blocked builtin: '{name}()'")
    return violations


# ---------------------------------------------------------------------------
# Human-in-the-loop gate
# ---------------------------------------------------------------------------
# Arbitrary code execution is a high-risk operation. Before running any
# script the plugin checks for an "_approved" flag in args. If absent it
# returns the __APPROVAL_REQUIRED__ sentinel so the frontend can present a
# confirmation dialog (showing the code to be run) before re-submitting with
# approved=True.
#
# Frontend integration (app.js):
#   ws.onmessage receives {"type": "approval_required", "command": "<code>"}
#   → render dialog: "Optimus wants to execute code. Approve?" with code preview.
#   On Approve: re-send original THINK command with approved:true in payload.
#   On Deny: dismiss, add denial log entry.
# ---------------------------------------------------------------------------

def execute(args: dict = None) -> str:
    if not args or "code" not in args:
        return "Error: No 'code' argument provided. Please supply the Python code to execute."

    code = args["code"]
    try:
        timeout = min(int(args.get("timeout", 10)), 60)
    except (ValueError, TypeError):
        timeout = 10
    approved = bool(args.get("approved", False) or args.get("_approved", False))

    # ── Gate: require explicit frontend approval ───────────────────────────
    if not approved:
        return f"__APPROVAL_REQUIRED__:{code}"

    # ── Gate: Static AST Analysis ──────────────────────────────────────────
    violations = _static_scan(code)
    if violations:
        v_list = ", ".join(violations)
        return f"__UNSAFE_CODE__:Blocked by static analysis: {v_list}"


    import uuid
    workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scratch"))
    os.makedirs(workspace, exist_ok=True)
    script_path = os.path.join(workspace, f"_optimus_script_{uuid.uuid4().hex[:8]}.py")

    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Map Windows path to WSL path
        drive, tail = os.path.splitdrive(script_path)
        wsl_script_path = f"/mnt/{drive[0].lower()}{tail.replace(os.sep, '/')}"

        import shutil
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        if sys.platform == "win32" and shutil.which("wsl"):
            cmd = ["wsl", "-e", "python3", wsl_script_path]
        else:
            cmd = [sys.executable, script_path]

        # We keep the timeout which provides an execution time limit for security
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace,
            creationflags=creationflags,
        )

        output = ""
        max_len = 10000
        if result.stdout:
            stdout_str = result.stdout[:max_len]
            if len(result.stdout) > max_len:
                stdout_str += "\n...[TRUNCATED]"
            output += f"STDOUT:\n{stdout_str}"
        if result.stderr:
            stderr_str = result.stderr[:max_len]
            if len(result.stderr) > max_len:
                stderr_str += "\n...[TRUNCATED]"
            output += f"\nSTDERR:\n{stderr_str}"
        if result.returncode != 0:
            output += f"\n(Exit code: {result.returncode})"

        return output.strip() or "(Script executed successfully with no output.)"

    except subprocess.TimeoutExpired:
        return f"Error: Script timed out after {timeout} seconds."
    except Exception as e:
        return f"Error running code: {e}"
    finally:
        # Cleanup the temp script
        try:
            if os.path.exists(script_path):
                os.remove(script_path)
        except Exception:
            pass
