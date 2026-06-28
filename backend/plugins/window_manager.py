import ctypes
import asyncio
import re

PLUGIN_METADATA = {
    "name": "window_manager",
    "description": "Lists running windows, or focuses/minimizes/closes specific application windows by title. Actions: 'list', 'focus', 'minimize', 'close'.",
    "keywords": ["window", "focus", "minimize", "close", "switch", "alt tab", "running", "active"]
}

user32 = ctypes.windll.user32

SW_MINIMIZE = 6
WM_CLOSE = 0x0010

import ctypes.wintypes
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.POINTER(ctypes.c_int))

def _get_window_text(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    return ""

def _is_visible(hwnd):
    return user32.IsWindowVisible(hwnd)

async def execute(args: dict = None) -> str:
    action = args.get("action", "list").lower() if args else "list"
    
    if action == "list":
        try:
            windows = []
            def enum_cb(hwnd, lParam):
                if _is_visible(hwnd):
                    title = _get_window_text(hwnd)
                    if title:
                        windows.append(title)
                return True
                
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            
            if windows:
                return f"Currently open windows:\n" + "\n".join(windows)
            else:
                return "No visible windows found."
        except Exception as e:
            return f"Error listing windows: {e}"
            
    elif action in ["focus", "minimize", "close"]:
        raw_target = args.get("title", "")
        if not raw_target:
            return "Error: Provide a 'title' argument to identify the target window."
            
        target = raw_target.lower()
        target_hwnd = [0]
        
        def enum_cb(hwnd, lParam):
            if _is_visible(hwnd):
                title = _get_window_text(hwnd)
                if title and target in title.lower():
                    target_hwnd[0] = hwnd
                    return False
            return True
            
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        hwnd = target_hwnd[0]
        
        if not hwnd:
            return f"No visible window found matching: '{raw_target}'"
            
        try:
            if action == "focus":
                user32.SetForegroundWindow(hwnd)
                return f"Focused window matching: '{raw_target}'"
            elif action == "minimize":
                user32.ShowWindow(hwnd, SW_MINIMIZE)
                return f"Minimized window matching: '{raw_target}'"
            elif action == "close":
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                return f"Closed window matching: '{raw_target}'"
        except Exception as e:
            return f"Error performing {action} on '{raw_target}': {e}"

    return f"Unknown action: {action}"
