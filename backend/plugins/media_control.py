import ctypes

PLUGIN_METADATA = {
    "name": "media_control",
    "description": "Controls the system volume and media playback using keyboard simulation.",
    "keywords": ["volume", "mute", "unmute", "play", "pause", "next", "previous", "stop", "music", "media"]
}

# Windows Virtual Key Codes
VK_CODES = {
    "playpause": 0xB3,
    "nexttrack": 0xB0,
    "prevtrack": 0xB1,
    "stop": 0xB2,
    "volumemute": 0xAD,
    "volumeup": 0xAF,
    "volumedown": 0xAE
}

def execute(args: dict = None) -> str:
    if not args:
        return "Error: Please provide an 'action' (e.g., 'play', 'pause', 'mute')."
    
    action = args.get("action")
    if not action:
        cmd = args.get("command", args.get("query", "")).lower().strip()
        for prefix in ["volume ", "mute", "unmute", "play", "pause", "next", "previous", "stop"]:
            if cmd.startswith(prefix):
                action = cmd.split()[0] if "volume" not in prefix else cmd.replace(" ", "")
                break
                
    if not action:
        return "Error: Please provide an 'action'."
        
    action = action.lower().replace("_", "").replace(" ", "")
    
    # Map friendly names to actual actions
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
        return f"Error: Unknown action '{action}'."
        
    try:
        vk_code = VK_CODES[mapped_action]
        
        def press_key(code):
            scan_code = ctypes.windll.user32.MapVirtualKeyA(code, 0)
            ctypes.windll.user32.keybd_event(code, scan_code, 0, 0) # Key Down
            ctypes.windll.user32.keybd_event(code, scan_code, 2, 0) # Key Up
            
        if mapped_action == "volumeup":
            for _ in range(5): press_key(vk_code)
        elif mapped_action == "volumedown":
            for _ in range(5): press_key(vk_code)
        else:
            press_key(vk_code)
            
        return f"Successfully executed media action: {mapped_action}"
    except Exception as e:
        return f"Error executing media control: {e}"
