import subprocess
import asyncio
import pyautogui

# ---------------------------------------------------------------------------
# Failsafe: moving mouse to the top-left corner of the screen immediately
# aborts any running pyautogui sequence. MUST remain True in production.
# ---------------------------------------------------------------------------
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

PLUGIN_METADATA = {
    "name": "desktop_automation",
    "description": (
        "Performs native automation inside desktop applications by launching them and running "
        "sequential keyboard/mouse/wait macros (e.g. typing, pressing shortcuts like 'enter' or "
        "'ctrl+p', or launching sub-processes)."
    ),
    "keywords": [
        "automate", "macro", "pyautogui", "keyboard", "shortcut",
        "type", "press", "control", "spotify", "vscode", "terminal",
    ],
}


async def execute(args: dict = None) -> str:
    if not args or "app_name" not in args:
        return "Error: App name ('app_name') argument is required. Operations list ('operations') is optional."

    approved = bool(args.get("_approved", args.get("approved", False)))
    if not approved:
        return f"__APPROVAL_REQUIRED__:desktop_automation:{args}"

    app_name = args.get("app_name", "").strip()
    operations = args.get("operations", [])

    # Normalise operations to list
    if isinstance(operations, str):
        import json
        try:
            operations = json.loads(operations)
        except Exception:
            operations = [{"action": "type", "text": operations}]

    if not isinstance(operations, list):
        operations = [operations]

    logs = [f"Deploying system automation routine for application: '{app_name}'"]

    try:
        for idx, op in enumerate(operations):
            if not isinstance(op, dict):
                logs.append(f"Step {idx+1}: Skipping invalid non-dict operation: {op}")
                continue

            action = op.get("action", "").lower().strip()
            logs.append(f"Step {idx+1}: {action} -> {op}")

            if action == "launch":
                cmd = op.get("command") or app_name
                # Spawn subprocess asynchronously without blocking
                await asyncio.create_subprocess_exec(
                    "cmd", "/c", "start", "", cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await asyncio.sleep(2.0)
            elif action == "type":
                text = op.get("text", "")
                await asyncio.to_thread(pyautogui.write, text, interval=0.04)
            elif action == "press":
                key = op.get("key", "")
                if "+" in key:
                    parts = [p.strip().lower() for p in key.split("+")]
                    await asyncio.to_thread(pyautogui.hotkey, *parts)
                else:
                    await asyncio.to_thread(pyautogui.press, key)
            elif action == "hotkey":
                keys = op.get("keys", [])
                await asyncio.to_thread(pyautogui.hotkey, *[k.strip().lower() for k in keys])
            elif action == "wait":
                secs = float(op.get("seconds", 1.0))
                await asyncio.sleep(secs)
            else:
                logs.append(f"Step {idx+1}: Warning - Unsupported action type '{action}' skipped.")

        return f"SUCCESS: Desktop automation routine completed for '{app_name}'.\n" + "\n".join(logs)
    except Exception as e:
        return f"ERROR executing desktop automation for '{app_name}': {str(e)}\nPartial execution log:\n" + "\n".join(logs)
