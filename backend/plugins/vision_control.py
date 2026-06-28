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

PLUGIN_METADATA = {
    "name": "vision_control",
    "description": "Uses Vision LLM to locate UI elements on screen and perform actions (click, type, drag, hotkey) based on natural language prompts.",
    "keywords": ["vision", "click", "screen", "ui", "find", "locate", "type", "drag"]
}

async def execute(args: dict = None) -> str:
    if not args or "prompt" not in args:
        return "Error: 'prompt' argument is required (e.g., 'Click the submit button')."
        
    prompt = args["prompt"]
    approved = bool(args.get("_approved", False) or args.get("approved", False))
    
    if not VISION_AVAILABLE:
        return "Error: Vision modules (pyautogui, mss, PIL) not installed."
        
    try:
        from backend.main import manager
        from backend.core.agent import OptimusAgent
        
        # We need an agent to run the vision inference
        agent = OptimusAgent()
        
        # 1. Capture Screen
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img.thumbnail((1024, 1024))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64_image = base64.b64encode(buf.getvalue()).decode('utf-8')
            
        # 2. VLM Inference
        vlm_prompt = (
            f"Find the UI element for '{prompt}'. Return JSON: "
            "{\"x\": int, \"y\": int, \"w\": int, \"h\": int, \"action\": \"click|type|drag\", \"text\": \"optional text to type\", \"target_x\": int, \"target_y\": int}"
        )
        response = await agent._llm_generate_vision(vlm_prompt, b64_image)
        
        # Clean JSON
        response = response.strip()
        if response.startswith("```json"): response = response[7:-3].strip()
        elif response.startswith("```"): response = response[3:-3].strip()
        
        cmd = json.loads(response)
        x, y = cmd.get("x"), cmd.get("y")
        w, h = cmd.get("w", 50), cmd.get("h", 50)
        action = cmd.get("action", "click")
        
        if not (x and y):
            return "Could not determine safe coordinates from the screen."
            
        # 3. Intercept and Wait for Approval
        if not approved:
            # We broadcast the intercept to all clients since we don't have the specific websocket here easily
            await manager.broadcast({
                "type": "vision_intercept",
                "data": {
                    "x": x, "y": y, "w": w, "h": h,
                    "action": action,
                    "text": cmd.get("text", "")
                }
            })
            # To actually wait, we just return the approval string
            return f"__APPROVAL_REQUIRED__:vision_control:{json.dumps(args)}"
            
        # 4. Execute Action
        if action == "click":
            await asyncio.to_thread(pyautogui.click, x, y)
        elif action == "type":
            await asyncio.to_thread(pyautogui.click, x, y)
            await asyncio.sleep(0.2)
            await asyncio.to_thread(pyautogui.write, cmd.get("text", ""), interval=0.04)
        elif action == "drag":
            tx, ty = cmd.get("target_x"), cmd.get("target_y")
            if tx and ty:
                await asyncio.to_thread(pyautogui.moveTo, x, y)
                await asyncio.to_thread(pyautogui.dragTo, tx, ty, duration=0.5)
            else:
                return "Drag action requires target_x and target_y."
        
        return f"Successfully executed '{action}' at ({x}, {y})."
        
    except Exception as e:
        logger.error(f"Visual execution failed: {e}")
        return f"Visual execution failed: {e}. Aborted to maintain system safety."
