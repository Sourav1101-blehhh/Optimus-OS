import subprocess

PLUGIN_METADATA = {
    "name": "clipboard",
    "description": "Reads from or writes to the system clipboard. Use action 'read' to get current clipboard content, or 'write' with a 'text' argument to copy text to clipboard.",
    "keywords": ["clipboard", "copy", "paste", "copied", "clip"]
}

import asyncio

async def execute(args: dict = None) -> str:
    action = args.get("action", "read").lower() if args else "read"
    
    if action == "read":
        try:
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-command", "Get-Clipboard",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            content = stdout.decode('utf-8').strip() if stdout else ""
            if content:
                return f"Current clipboard content:\n{content}"
            else:
                return "Clipboard is empty."
        except Exception as e:
            return f"Error reading clipboard: {e}"
    
    elif action == "write":
        text = args.get("text", "")
        if not text:
            return "Error: No 'text' provided to copy to clipboard."
        try:
            # Use powershell Set-Clipboard
            # Write to stdin instead of injecting in the command line
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-command", "Set-Clipboard",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(proc.communicate(input=text.encode('utf-8')), timeout=5.0)
            return f"Successfully copied to clipboard: {text[:100]}{'...' if len(text) > 100 else ''}"
        except Exception as e:
            return f"Error writing to clipboard: {e}"
    
    return f"Unknown action: {action}. Use 'read' or 'write'."
