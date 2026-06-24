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
    "spotify": "spotify:",
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
    if not args:
        return "Error: Please provide an 'app' argument with the application name to launch."
    
    app_name = args.get("app")
    if not app_name:
        cmd = args.get("command", args.get("query", "")).lower().strip()
        for prefix in ["open ", "launch ", "start ", "run "]:
            if cmd.startswith(prefix):
                app_name = cmd[len(prefix):].strip()
                break
                
    if not app_name:
        return "Error: Please provide an 'app' argument with the application name to launch."
        
    app_name = app_name.lower().strip()
    
    # Look up in the map first
    executable = APP_MAP.get(app_name, app_name)
    
    try:
        # os.startfile inherits headless state from Uvicorn, which hides UWP apps like Spotify.
        # Passing it to 'explorer' forces it to spawn in the active desktop UI session.
        if executable.endswith(":"):
            subprocess.run(["explorer", executable], shell=True)
        else:
            os.startfile(executable)
        return f"Successfully launched: {app_name}"
    except Exception as e:
        return f"Error: launching '{app_name}' failed: {e}"
