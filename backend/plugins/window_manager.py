import subprocess
import re

PLUGIN_METADATA = {
    "name": "window_manager",
    "description": "Lists running windows, or focuses/minimizes/closes specific application windows by title. Actions: 'list', 'focus', 'minimize', 'close'.",
    "keywords": ["window", "focus", "minimize", "close", "switch", "alt tab", "running", "active"]
}

import asyncio
import re

def _sanitize_title(title: str) -> str:
    """Strip malicious PowerShell chars."""
    return re.sub(r"[;'\"|&$\n\r]", "", title)

async def execute(args: dict = None) -> str:
    action = args.get("action", "list").lower() if args else "list"
    
    if action == "list":
        try:
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-command",
                "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object ProcessName, MainWindowTitle | Format-Table -AutoSize",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            windows = stdout.decode('utf-8').strip() if stdout else ""
            
            if windows:
                return f"Currently open windows:\n{windows}"
            else:
                return "No visible windows found."
        except Exception as e:
            return f"Error listing windows: {e}"
    
    elif action in ["focus", "minimize", "close"]:
        raw_target = args.get("title", "")
        if not raw_target:
            return "Error: Provide a 'title' argument to identify the target window."
            
        target = _sanitize_title(raw_target)
        
        try:
            if action == "focus":
                ps_cmd = f"""
                Add-Type @"
                    using System;
                    using System.Runtime.InteropServices;
                    public class Win32 {{
                        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
                    }}
"@
                $proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{target}*' }} | Select-Object -First 1
                if ($proc) {{ [Win32]::SetForegroundWindow($proc.MainWindowHandle) }}
                """
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-command", ps_cmd,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await asyncio.wait_for(proc.communicate(), timeout=5.0)
                return f"Focused window matching: '{target}'"
            
            elif action == "minimize":
                ps_cmd = f"""
                $proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{target}*' }} | Select-Object -First 1
                if ($proc) {{
                    Add-Type @"
                        using System;
                        using System.Runtime.InteropServices;
                        public class Win32Min {{
                            [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                        }}
"@
                    [Win32Min]::ShowWindow($proc.MainWindowHandle, 6)
                }}
                """
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-command", ps_cmd,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await asyncio.wait_for(proc.communicate(), timeout=5.0)
                return f"Minimized window matching: '{target}'"
            
            elif action == "close":
                ps_cmd = f"Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{target}*' }} | Stop-Process -Force"
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-command", ps_cmd,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await asyncio.wait_for(proc.communicate(), timeout=5.0)
                return f"Closed window matching: '{target}'"
        except Exception as e:
            return f"Error performing {action} on '{target}': {e}"
    
    return f"Unknown action: {action}"
