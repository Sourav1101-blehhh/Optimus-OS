import subprocess
import tempfile
import os

PLUGIN_METADATA = {
    "name": "code_runner",
    "description": (
        "Writes a Python script to a temporary file, executes it, and returns the output. "
        "Use this to run any custom code the user requests."
    ),
    "keywords": ["code", "run", "execute", "python", "script", "calculate", "compute", "program"],
}

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
    timeout = args.get("timeout", 15)
    approved = args.get("_approved", False)

    # ── Gate: require explicit frontend approval ───────────────────────────
    if not approved:
        return f"__APPROVAL_REQUIRED__:{code}"

    workspace = os.path.join(os.path.dirname(__file__), "..", "..", "scratch")
    os.makedirs(workspace, exist_ok=True)
    script_path = os.path.join(workspace, "_optimus_script.py")

    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        result = subprocess.run(
            ["python", script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace,
        )

        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}"
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n(Exit code: {result.returncode})"

        return output.strip() or "(Script executed successfully with no output.)"

    except subprocess.TimeoutExpired:
        return f"Error: Script timed out after {timeout} seconds."
    except Exception as e:
        return f"Error running code: {e}"
    finally:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except Exception:
                pass
