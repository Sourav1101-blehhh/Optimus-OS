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
# AST Static Analysis Gate (DRY RUN MODE)
# ---------------------------------------------------------------------------
import ast
import logging

logger = logging.getLogger(__name__)

# Strict allowlist of safe modules
_ALLOWED_MODULES = {"math", "datetime", "json", "re", "random", "itertools", "collections", "time", "uuid", "hashlib"}
_ALLOWED_BUILTINS = {"print", "len", "range", "int", "float", "str", "list", "dict", "set", "tuple", "bool", "sum", "min", "max", "abs", "round", "enumerate", "zip", "map", "filter", "any", "all", "type", "isinstance", "issubclass", "getattr", "hasattr", "open", "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "sorted", "reversed"}
_ALLOWED_NODES = {
    ast.Module, ast.Expr, ast.Call, ast.Name, ast.Load, ast.Store, ast.Assign,
    ast.Constant, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.UnaryOp, ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn, ast.If, ast.For,
    ast.While, ast.Break, ast.Continue, ast.Pass, ast.FunctionDef, ast.Return,
    ast.arguments, ast.arg, ast.Dict, ast.List, ast.Set, ast.Tuple, ast.Subscript,
    ast.Index, ast.Slice, ast.ExtSlice, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp, ast.comprehension, ast.keyword, ast.Attribute,
    ast.Import, ast.ImportFrom, ast.alias, ast.ClassDef, ast.FormattedValue,
    ast.JoinedStr, ast.Try, ast.ExceptHandler, ast.Raise, ast.Assert, ast.IfExp,
    ast.Del, ast.With, ast.withitem, ast.Yield, ast.YieldFrom, ast.Global,
    ast.Nonlocal, ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith
}

def _static_scan(code: str) -> list[str]:
    """Returns list of violation strings. In dry run mode, just logs them."""
    violations = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        violations.append(f"SyntaxError: {e}")
        return violations
    
    for node in ast.walk(tree):
        # 1. Check Node Type
        if type(node) not in _ALLOWED_NODES:
            violations.append(f"Blocked AST Node: {type(node).__name__}")
            continue

        # 2. Check Imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                module_name = node.module.split(".")[0]
                if module_name not in _ALLOWED_MODULES:
                    violations.append(f"Blocked import: '{module_name}'")
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name not in _ALLOWED_MODULES:
                    violations.append(f"Blocked import: '{name}'")
                    
        # 3. Check Function Calls
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id not in _ALLOWED_BUILTINS and not func.id.startswith("_"):
                    # We can't definitively know if it's a builtin or user-defined function just from AST without scope analysis,
                    # but for a strict sandbox we could block unknown names. 
                    # For dry run, we'll log it.
                    violations.append(f"Potentially blocked call: '{func.id}()'")
            elif isinstance(func, ast.Attribute):
                if func.attr.startswith("__"):
                    violations.append(f"Blocked dunder call: '{func.attr}()'")
                    
        # 4. Check Attribute Access (block __class__, __subclasses__, etc.)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                violations.append(f"Blocked dunder attribute: '{node.attr}'")

    if violations:
        logger.warning(f"code_runner.py blocking execution due to: {', '.join(violations)}")
        return violations
    return violations

async def execute(args: dict = None) -> str:
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

    # Route to Docker if available
    try:
        from backend.plugins.docker_runner import sandbox_runner
        if sandbox_runner.available:
            return await sandbox_runner.execute_code(code)
    except Exception as e:
        logger.warning(f"Docker sandbox failed, falling back to AST: {e}")

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
            output = f"Error: Script failed with exit code {result.returncode}\n{output}"

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
