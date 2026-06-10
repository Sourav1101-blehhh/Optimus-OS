"""
main.py — Optimus OS Backend Gateway v5.1
==========================================
Architecture: FastAPI + Starlette WebSocket + asyncio
Security:     HMAC-SHA256 master password gateway (persistent across restarts)
Isolation:    Per-connection OptimusAgent instantiation (no shared conversation state)
Routing:      Regex word-boundary semantic intent router (no greedy prefix collisions)
Telemetry:    Isolated asyncio background task pushing CPU/RAM at 1 Hz
Daemons:      Offline Wake-Word (VosK) & Proactive Scheduler (APScheduler)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from typing import Optional

# ---------------------------------------------------------------------------
# Ollama performance flags — must precede all other imports
# ---------------------------------------------------------------------------
os.environ.setdefault("OLLAMA_FLASH_ATTENTION", "1")
os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", "2")

# ---------------------------------------------------------------------------
# Path resolution: ensure backend package is importable regardless of CWD
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.abspath(__file__))
for _entry in (_ROOT, os.path.dirname(_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

# uvloop accelerates the event loop on POSIX systems; harmless skip on Windows
if sys.platform != "win32":
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

import psutil
try:
    import py3nvml
    import wmi
    try:
        py3nvml.py3nvml.nvmlInit()
        HAS_GPU_WMI = True
    except Exception:
        HAS_GPU_WMI = False
except ImportError:
    HAS_GPU_WMI = False

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) -> %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("OptimusCore")

# ---------------------------------------------------------------------------
# Persistent HMAC-SHA256 Security Gateway
# ---------------------------------------------------------------------------
_MASTER_PW_RAW: str = os.getenv("OPTIMUS_MASTER_PASSWORD", "R136a1IC1101@")
MASTER_PW_HASH: bytes = hashlib.sha256(_MASTER_PW_RAW.encode("utf-8")).digest()
logger.info(
    "Security gateway armed.  SHA-256 of master password loaded "
    "(env: OPTIMUS_MASTER_PASSWORD).  Password persists across restarts."
)

def _verify_password(candidate: str) -> bool:
    candidate_hash = hashlib.sha256(candidate.encode("utf-8")).digest()
    return hmac.compare_digest(MASTER_PW_HASH, candidate_hash)


# ---------------------------------------------------------------------------
# Core imports
# ---------------------------------------------------------------------------
from backend.core.agent import OptimusAgent           
from backend.core.plugin_manager import plugin_manager  
from backend.core.audio_engine import wake_word_engine, WAKE_EVENT_QUEUE
from backend.core.scheduler import optimus_scheduler

# ---------------------------------------------------------------------------
# Pydantic v2 WebSocket frame schema
# ---------------------------------------------------------------------------
class WebSocketMessage(BaseModel):
    command: str
    text: Optional[str] = None
    engine: Optional[str] = "LOCAL"
    image_data: Optional[str] = None
    approved: Optional[bool] = False
    token: Optional[str] = None


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(plugin_manager.load_plugins)
    logger.info(f"Plugin registry loaded: {len(plugin_manager.plugins)} plugins active.")

    # Start Daemons
    wake_word_engine.start()
    optimus_scheduler.start()

    telemetry_task = asyncio.create_task(hardware_telemetry_loop(), name="telemetry")
    wake_listener = asyncio.create_task(wake_word_listener(), name="wake_listener")
    logger.info("Isolated telemetry & wake-word background tasks started.")

    yield  

    telemetry_task.cancel()
    wake_listener.cancel()
    wake_word_engine.stop()
    try:
        await telemetry_task
        await wake_listener
    except asyncio.CancelledError:
        pass
    
    if HAS_GPU_WMI:
        try:
            py3nvml.py3nvml.nvmlShutdown()
        except Exception:
            pass
            
    logger.info("Optimus v5.1 backend shut down cleanly.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(title="Optimus Backend", version="5.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Connection Manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._agents: dict[WebSocket, OptimusAgent] = {}

    async def connect(self, websocket: WebSocket) -> OptimusAgent:
        self.active_connections.append(websocket)
        agent = OptimusAgent()          
        self._agents[websocket] = agent
        logger.info(f"Neural link established.  Active links: {len(self.active_connections)}")
        plugins = plugin_manager.get_all_metadata()
        await self.send_system_message(websocket, "Connected to Optimus Core v5.1 (Authenticated).")
        await self.safe_send_json(websocket, {"type": "plugins", "data": plugins})
        return agent

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self._agents:
            del self._agents[websocket]
        logger.warning(f"Neural link severed.  Active links: {len(self.active_connections)}")

    async def safe_send_json(self, websocket: WebSocket, payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except Exception as exc:
            logger.error(f"Failed to transmit payload: {exc}")
            self.disconnect(websocket)

    async def safe_send_text(self, websocket: WebSocket, text: str) -> None:
        try:
            await websocket.send_text(text)
        except Exception as exc:
            logger.error(f"Failed to transmit text frame: {exc}")
            self.disconnect(websocket)

    async def send_system_message(self, websocket: WebSocket, message: str) -> None:
        await self.safe_send_json(websocket, {"type": "log", "data": message})

    async def send_state(self, websocket: WebSocket, state: str) -> None:
        await self.safe_send_json(websocket, {"type": "state", "data": state})

    async def broadcast(self, payload: dict) -> None:
        if not self.active_connections:
            return
        tasks = [self.safe_send_json(ws, payload) for ws in self.active_connections]
        await asyncio.gather(*tasks, return_exceptions=True)

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# Wake Word Queue Listener
# ---------------------------------------------------------------------------
async def wake_word_listener():
    """Listens for IPC events from the Vosk audio thread."""
    while True:
        try:
            await WAKE_EVENT_QUEUE.get()
            logger.info("Wake-word event consumed from IPC queue. Triggering clients.")
            # Force-activate client handshake focus
            await manager.broadcast({"type": "wake_word_detected", "data": "Hey Optimus"})
            
            if not manager.active_connections:
                logger.info("No active frontend connections detected. Launching Optimus UI.")
                # Use msedge in app mode since it supports PWAs natively on Windows
                os.system("start msedge --app=http://127.0.0.1:8080")
        except Exception as e:
            logger.error(f"Wake word listener error: {e}")

# ---------------------------------------------------------------------------
# Isolated Telemetry Background Task
# ---------------------------------------------------------------------------
async def hardware_telemetry_loop() -> None:
    logger.info("Telemetry engine started.")
    w_sys = wmi.WMI() if HAS_GPU_WMI else None
    
    while True:
        try:
            if manager.active_connections:
                cpu = await asyncio.to_thread(psutil.cpu_percent, interval=None)
                ram = await asyncio.to_thread(lambda: psutil.virtual_memory().percent)
                
                payload = {"type": "telemetry", "cpu": round(cpu, 1), "ram": round(ram, 1)}
                
                # Extended telemetry if available
                if HAS_GPU_WMI:
                    try:
                        handle = await asyncio.to_thread(py3nvml.py3nvml.nvmlDeviceGetHandleByIndex, 0)
                        util = await asyncio.to_thread(py3nvml.py3nvml.nvmlDeviceGetUtilizationRates, handle)
                        temp = await asyncio.to_thread(py3nvml.py3nvml.nvmlDeviceGetTemperature, handle, py3nvml.py3nvml.NVML_TEMPERATURE_GPU)
                        payload["gpu_pct"] = util.gpu
                        payload["gpu_temp"] = temp
                    except Exception:
                        pass
                        
                frame = json.dumps(payload)
                tasks = [manager.safe_send_text(ws, frame) for ws in manager.active_connections]
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            logger.error(f"Telemetry loop error: {exc}")
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# HTTP Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok", "version": "5.1", "plugins": len(plugin_manager.plugins)}

@app.get("/")
def read_root():
    return {"message": "Optimus Core v5.1 is online."}

@app.get("/plugins")
def get_plugins():
    return {"plugins": plugin_manager.get_all_metadata()}


# ---------------------------------------------------------------------------
# Upgraded Semantic Router
# ---------------------------------------------------------------------------
_RAW_ROUTING_TABLE: dict[str, str] = {
    "open":        "app_launcher",
    "launch":      "app_launcher",
    "start":       "app_launcher",
    "close":       "app_launcher",
    "run":         "terminal",
    "kill":        "terminal",
    "volume":      "media_control",
    "mute":        "media_control",
    "unmute":      "media_control",
    "brightness":  "system_vitals",
    "lock screen": "system_vitals",
    "sleep":       "system_vitals",
    "restart":     "system_vitals",
    "shutdown":    "system_vitals",
    "screenshot":  "screenshot",
    "search":      "web_search",
    "weather":     "weather",
    "email":       "google_mail",
    "mail":        "google_mail",
    "calendar":    "google_calendar",
    "schedule":    "google_calendar",
    "meeting":     "google_calendar",
    "appointment": "google_calendar",
}

_SEMANTIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"^{re.escape(kw)}\b", re.IGNORECASE), plugin)
    for kw, plugin in sorted(_RAW_ROUTING_TABLE.items(), key=lambda kv: len(kv[0]), reverse=True)
]

def get_semantic_route(text: str) -> Optional[str]:
    stripped = text.strip()
    for pattern, plugin_name in _SEMANTIC_PATTERNS:
        if pattern.match(stripped):
            return plugin_name
    return None


# ---------------------------------------------------------------------------
# Unified WebSocket Gateway — /ws
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        auth_payload = json.loads(raw_auth)
        candidate_pw = str(auth_payload.get("password", auth_payload.get("token", "")))

        if not _verify_password(candidate_pw):
            logger.warning("Rejecting WebSocket: Invalid password.")
            await websocket.close(code=1008, reason="Unauthorized")
            return

    except asyncio.TimeoutError:
        logger.warning("Rejecting WebSocket: Auth timeout (5 s).")
        try:
            await websocket.close(code=1008, reason="Auth timeout")
        except RuntimeError:
            pass
        return
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.close(code=1008, reason="Unauthorized")
        except RuntimeError:
            pass
        return

    agent = await manager.connect(websocket)

    try:
        while True:
            raw_data = await websocket.receive_text()

            try:
                payload = WebSocketMessage.model_validate(json.loads(raw_data))
            except (json.JSONDecodeError, ValidationError) as exc:
                await manager.send_system_message(websocket, "Error: Invalid or malformed JSON frame — ignored.")
                continue

            if payload.command != "THINK":
                await manager.send_system_message(websocket, f"Unknown command '{payload.command}' — ignored.")
                continue

            user_msg    = (payload.text or "").strip()
            engine      = (payload.engine or "LOCAL").upper()
            image_data  = payload.image_data
            approved    = bool(payload.approved)

            if not user_msg:
                continue

            await manager.send_state(websocket, "thinking")

            route = get_semantic_route(user_msg)
            if route and not image_data:
                try:
                    result = await agent.execute_plugin_async(
                        route,
                        {"command": user_msg, "query": user_msg, "_approved": approved},
                    )
                except Exception as exc:
                    result = f"Local plugin error: {exc}"

                await manager.send_state(websocket, "idle")

                if isinstance(result, str) and result.startswith("__APPROVAL_REQUIRED__:"):
                    cmd_text = result[len("__APPROVAL_REQUIRED__:"):]
                    await manager.safe_send_json(websocket, {"type": "approval_required", "command": cmd_text})
                else:
                    await manager.safe_send_json(websocket, {"type": "chat", "data": f"[LOCAL] {result}"})
                continue

            try:
                async for token_piece in agent.process_message_stream(
                    user_msg, image_data=image_data, engine=engine
                ):
                    await manager.safe_send_text(websocket, token_piece)

                await manager.safe_send_json(websocket, {"type": "stream_end"})
            except Exception as exc:
                logger.error(f"Orchestrator stream error: {exc}")
                await manager.safe_send_json(websocket, {"type": "chat", "data": f"[ERROR] Inference error: {exc}"})

            await manager.send_state(websocket, "idle")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
