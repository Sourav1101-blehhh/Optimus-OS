import pyautogui
import base64
import io
import os

PLUGIN_METADATA = {
    "name": "screenshot",
    "description": "Takes a screenshot of the current screen and returns it as base64 image data for visual analysis by the AI.",
    "keywords": ["screenshot", "screen", "capture", "what's on my screen", "show me", "look at my screen", "display"]
}

def execute(args: dict = None) -> str:
    try:
        # Take the screenshot
        img = pyautogui.screenshot()
        
        # Convert to bytes
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        img_bytes = buffer.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')
        
        # Save a copy locally for reference
        save_path = os.path.join(os.path.dirname(__file__), "..", "..", "last_screenshot.png")
        img.save(save_path)
        
        return f"SCREENSHOT_BASE64:{img_b64}"
    except Exception as e:
        return f"Error capturing screenshot: {e}"
