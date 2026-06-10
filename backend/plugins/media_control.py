import pyautogui

PLUGIN_METADATA = {
    "name": "media_control",
    "description": "Controls the system volume and media playback using keyboard simulation.",
    "keywords": ["volume", "mute", "unmute", "play", "pause", "next", "previous", "stop", "music", "media"]
}

def execute(args: dict = None) -> str:
    if not args or "action" not in args:
        return "Error: Please provide an 'action' (e.g., 'playpause', 'nexttrack', 'prevtrack', 'volumemute', 'volumeup', 'volumedown')."
    
    action = args["action"].lower().replace("_", "").replace(" ", "")
    
    # Map friendly names to pyautogui key names
    action_map = {
        "play": "playpause",
        "pause": "playpause",
        "playpause": "playpause",
        "next": "nexttrack",
        "nexttrack": "nexttrack",
        "previous": "prevtrack",
        "prevtrack": "prevtrack",
        "mute": "volumemute",
        "unmute": "volumemute",
        "volumemute": "volumemute",
        "volumeup": "volumeup",
        "up": "volumeup",
        "volumedown": "volumedown",
        "down": "volumedown"
    }
    
    mapped_action = action_map.get(action)
    
    if not mapped_action:
        return f"Error: Unknown action '{action}'. Valid actions: {list(action_map.keys())}"
        
    try:
        if mapped_action == "volumeup":
            for _ in range(5): pyautogui.press("volumeup")
        elif mapped_action == "volumedown":
            for _ in range(5): pyautogui.press("volumedown")
        else:
            pyautogui.press(mapped_action)
            
        return f"Successfully executed media action: {mapped_action}"
    except Exception as e:
        return f"Error executing media control: {e}"
