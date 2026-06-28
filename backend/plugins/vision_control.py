import asyncio
import base64
import io
import json
import logging
from typing import Dict

try:
    import pyautogui
    import mss
    from PIL import Image
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

logger = logging.getLogger("VisionController")

class VisionController:
    def __init__(self):
        self.available = VISION_AVAILABLE
        if self.available:
            pyautogui.FAILSAFE = True  # Moving mouse to corner aborts!

    def _capture_screen_base64(self) -> str:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Compress for API overhead
            img.thumbnail((1024, 1024))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            return base64.b64encode(buf.getvalue()).decode('utf-8')

    async def execute_visual_action(self, action_prompt: str, agent, manager, websocket) -> str:
        """
        Execute visual action.
        agent: OptimusAgent instance
        manager: ConnectionManager (to send UI overlays)
        websocket: the current client socket
        """
        if not self.available:
            return "Vision modules not installed."

        try:
            b64_image = await asyncio.to_thread(self._capture_screen_base64)
            
            # Ask VLM for coordinates
            vlm_prompt = f"Find the UI element for '{action_prompt}'. Return JSON: {{\"x\": int, \"y\": int, \"w\": int, \"h\": int, \"action\": \"click|type\", \"text\": \"optional\"}}"
            response = await agent._llm_generate_vision(vlm_prompt, b64_image)
            
            # Clean JSON response
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:-3].strip()
            elif response.startswith("```"):
                response = response[3:-3].strip()
                
            cmd = json.loads(response)
            x, y = cmd.get("x"), cmd.get("y")
            w, h = cmd.get("w", 50), cmd.get("h", 50)
            
            if x and y:
                # Guided Mode Interception
                # Send bounding box overlay to UI
                await manager.safe_send_json(websocket, {
                    "type": "vision_intercept",
                    "data": {
                        "x": x, "y": y, "w": w, "h": h,
                        "action": cmd.get("action", "click"),
                        "text": cmd.get("text", "")
                    }
                })
                
                # Wait for user approval
                approved = agent.check_and_consume_approval(f"VISION_{x}_{y}") # We will simulate this or use the existing approval flow
                
                # For this implementation, we will log the intercept and assume guided mode handles it.
                # In full auto (if we add a toggle), we bypass this wait.
                
                return f"Intercepted action at ({x}, {y}). Awaiting user approval..."
            return "Could not determine safe coordinates."
        except Exception as e:
            logger.error(f"Visual execution failed: {e}")
            return f"Visual execution failed: {e}. Aborted to maintain system safety."

vision_controller = VisionController()
