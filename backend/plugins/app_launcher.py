import subprocess
import os

PLUGIN_METADATA = {
    "name": "app_launcher",
    "description": "Launches desktop applications by name on Windows. Examples: 'notepad', 'calculator', 'explorer', 'chrome', 'spotify', 'code' (VS Code).",
    "keywords": ["open", "launch", "start", "run", "app", "application", "program", "notepad", "calculator", "chrome", "spotify"]
}

# Common app name -> executable mapping for Windows
APP_MAP = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "paint": "mspaint.exe",
    "task manager": "taskmgr.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "settings": "ms-settings:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "spotify": "spotify",
    "discord": "discord",
    "slack": "slack",
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
}

def execute(args: dict = None) -> str:
    if not args or "app" not in args:
        return "Error: Please provide an 'app' argument with the application name to launch."
    
    app_name = args["app"].lower().strip()
    
    # Look up in the map first
    executable = APP_MAP.get(app_name, app_name)
    
    try:
        # Use 'start' on Windows for best compatibility
        if executable.startswith("ms-"):
            # UWP/Settings URI
            os.startfile(executable)
        else:
            import asyncio
            # If called from an async context, launch asynchronously
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    asyncio.create_subprocess_exec(
                        "cmd", "/c", "start", "", executable,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                )
            except RuntimeError:
                # Fallback if called synchronously
                subprocess.Popen(
                    ["cmd", "/c", "start", "", executable],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        return f"Successfully launched: {app_name}"
    except Exception as e:
        return f"Error launching '{app_name}': {e}"
