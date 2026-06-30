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
import secrets

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

if sys.platform != "win32":
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass
else:
    try:
        import winloop
        asyncio.set_event_loop_policy(winloop.EventLoopPolicy())
    except ImportError:
        pass

import psutil
try:
    import py3nvml
    if sys.platform == "win32":
        import wmi
    try:
        py3nvml.py3nvml.nvmlInit()
        HAS_GPU_WMI = True if sys.platform == "win32" else False
    except Exception:
        HAS_GPU_WMI = False
except ImportError:
    HAS_GPU_WMI = False

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError, Field

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
_MASTER_PW_RAW: str = os.getenv("OPTIMUS_MASTER_PASSWORD", "")
if not _MASTER_PW_RAW or _MASTER_PW_RAW == "CHANGE_ME_IN_PRODUCTION":
    _MASTER_PW_RAW = secrets.token_urlsafe(32)
    logger.warning("No secure master password in .env! Generated random one-time token (check console output manually if needed, not logged).")

MASTER_PW_HASH: bytes = hashlib.sha256(_MASTER_PW_RAW.encode("utf-8")).digest()
logger.info(
    "Security gateway armed. SHA-256 of master password loaded. "
    "Password persists across restarts if set in .env."
)

def _verify_password(candidate: str) -> bool:
    if len(candidate) == 64:
        try:
            candidate_bytes = bytes.fromhex(candidate)
            return hmac.compare_digest(MASTER_PW_HASH, candidate_bytes)
        except ValueError:
            pass
    candidate_hash = hashlib.sha256(candidate.encode("utf-8")).digest()
    return hmac.compare_digest(MASTER_PW_HASH, candidate_hash)


# ---------------------------------------------------------------------------
# Core imports
# ---------------------------------------------------------------------------
from backend.core.agent import OptimusAgent           
from backend.core.plugin_manager import plugin_manager  
from backend.core.audio_engine import wake_word_engine, get_wake_queue, stream_neural_tts
from backend.core.scheduler import optimus_scheduler

# ---------------------------------------------------------------------------
# Pydantic v2 WebSocket frame schema
# ---------------------------------------------------------------------------
class WebSocketMessage(BaseModel):
    command: str = Field(max_length=100)
    text: Optional[str] = Field(default=None, max_length=1000000)
    engine: Optional[str] = "LOCAL"
    image_data: Optional[str] = None
    approved: Optional[bool] = False
    token: Optional[str] = None
    rating: Optional[int] = 0


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
    
    from backend.core.daemon import start_daemons
    start_daemons()

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
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:8081", "http://127.0.0.1:8081", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Connection Manager & Rate Limiting
# ---------------------------------------------------------------------------
_GLOBAL_MSG_TIMESTAMPS: list[float] = []
_GLOBAL_RATE_LIMIT     = int(os.getenv("OPTIMUS_GLOBAL_RATE_LIMIT", "20"))  # msgs per 5s
_GLOBAL_RATE_WINDOW    = 5.0  # seconds

def _check_global_rate() -> bool:
    """Returns True if request is allowed, False if globally rate limited."""
    now = asyncio.get_running_loop().time()
    _GLOBAL_MSG_TIMESTAMPS[:] = [t for t in _GLOBAL_MSG_TIMESTAMPS if now - t < _GLOBAL_RATE_WINDOW]
    if len(_GLOBAL_MSG_TIMESTAMPS) >= _GLOBAL_RATE_LIMIT:
        return False
    _GLOBAL_MSG_TIMESTAMPS.append(now)
    return True

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._agents: dict[WebSocket, OptimusAgent] = {}
        self._locks: dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket) -> OptimusAgent:
        self.active_connections.append(websocket)
        self._locks[websocket] = asyncio.Lock()
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
        agent = self._agents.get(websocket)
        if agent:
            asyncio.create_task(agent.close())
            del self._agents[websocket]
        if websocket in self._locks:
            del self._locks[websocket]
        logger.warning(f"Neural link severed.  Active links: {len(self.active_connections)}")

    async def safe_send_json(self, websocket: WebSocket, payload: dict) -> None:
        lock = self._locks.get(websocket)
        if not lock: return
        async with lock:
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.error(f"Failed to transmit payload: {exc}")
                self.disconnect(websocket)

    async def safe_send_text(self, websocket: WebSocket, text: str) -> None:
        lock = self._locks.get(websocket)
        if not lock: return
        async with lock:
            try:
                await websocket.send_text(text)
            except Exception as exc:
                logger.error(f"Failed to transmit text frame: {exc}")
                self.disconnect(websocket)

    async def safe_send_bytes(self, websocket: WebSocket, data: bytes) -> None:
        lock = self._locks.get(websocket)
        if not lock: return
        async with lock:
            try:
                await websocket.send_bytes(data)
            except Exception as exc:
                logger.error(f"Failed to transmit bytes frame: {exc}")
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
optimus_scheduler.register_broadcast_fn(manager.broadcast)


# ---------------------------------------------------------------------------
# Wake Word Queue Listener
# ---------------------------------------------------------------------------
async def wake_word_listener():
    """Listens for IPC events from the Vosk audio thread."""
    while True:
        try:
            q = get_wake_queue()
            await q.get()
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
    
    last_net = None
    last_time = None
    
    while True:
        try:
            if manager.active_connections:
                now = asyncio.get_running_loop().time()
                cpu = await asyncio.to_thread(psutil.cpu_percent, interval=None)
                ram = await asyncio.to_thread(lambda: psutil.virtual_memory().percent)
                disk = await asyncio.to_thread(lambda: psutil.disk_usage(os.path.abspath(os.sep)).percent)
                net = await asyncio.to_thread(psutil.net_io_counters)
                
                net_up = 0.0
                net_down = 0.0
                if last_net and last_time and (now - last_time) > 0:
                    dt = now - last_time
                    net_up = (net.bytes_sent - last_net.bytes_sent) / dt / 1024 / 1024 # MB/s
                    net_down = (net.bytes_recv - last_net.bytes_recv) / dt / 1024 / 1024 # MB/s
                
                last_net = net
                last_time = now
                
                payload = {
                    "type": "telemetry", 
                    "cpu": round(cpu, 1), 
                    "ram": round(ram, 1),
                    "disk": round(disk, 1),
                    "net_up": round(net_up, 2),
                    "net_down": round(net_down, 2)
                }
                
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
    "volume":      "media_control",
    "mute":        "media_control",
    "unmute":      "media_control",
    "brightness":  "system_vitals",
    "lock screen": "system_vitals",
    "sleep":       "system_vitals",
    "restart":     "system_vitals",
    "shutdown":    "system_vitals",
    "screenshot":  "screenshot",
}

_SEMANTIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE), plugin)
    for kw, plugin in sorted(_RAW_ROUTING_TABLE.items(), key=lambda kv: len(kv[0]), reverse=True)
]

def get_semantic_route(text: str) -> Optional[str]:
    stripped = text.strip()
    for pattern, plugin_name in _SEMANTIC_PATTERNS:
        if pattern.search(stripped):
            return plugin_name
    return None


# ---------------------------------------------------------------------------
# Unified WebSocket Gateway — /ws
# ---------------------------------------------------------------------------
from fastapi import Query
from backend.core.security import validate_boot_token

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)) -> None:
    if not validate_boot_token(token):
        logger.warning("Rejecting WebSocket: Invalid or missing boot token.")
        try:
            await websocket.close(code=1008, reason="Unauthorized")
        except RuntimeError:
            pass
        return

    if len(manager.active_connections) >= 5:
        logger.warning("Max WebSocket connections reached. Rejecting new connection before handshake.")
        try:
            await websocket.close(code=1013, reason="Server busy")
        except RuntimeError:
            pass
        return

    await websocket.accept()

    try:
        raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        try:
            auth_payload = json.loads(raw_auth)
        except json.JSONDecodeError:
            auth_payload = {}
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
    if agent is None:
        return

    # ── Ollama Preloading Hook ──
    async def preload_ollama():
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:11434/api/generate",
                    json={"model": "qwen2.5-coder:7b", "prompt": "", "keep_alive": "10m"},
                    timeout=5.0
                )
        except Exception:
            pass
    asyncio.create_task(preload_ollama())

    message_timestamps = []

    try:
        while True:
            raw_data = await websocket.receive_text()
            if len(raw_data) > 1024 * 1024:
                logger.warning("Closing connection: Payload exceeded 1MB limit.")
                await websocket.close(code=1009, reason="Payload too large")
                return

            # ── WebSocket Rate Limiting (10 msgs / 5s) ──
            if not _check_global_rate():
                await manager.safe_send_json(websocket, {"type": "rate_limited", "data": "Global rate limit exceeded. Please slow down."})
                continue
                
            now = asyncio.get_running_loop().time()
            message_timestamps = [t for t in message_timestamps if now - t < 5.0]
            if len(message_timestamps) >= 10:
                await manager.safe_send_json(websocket, {"type": "rate_limited", "data": "Rate limit exceeded. Please slow down."})
                continue
            message_timestamps.append(now)

            try:
                payload_dict = json.loads(raw_data)
                payload_dict.pop("approved", None)
                payload_dict.pop("_approved", None)
                payload = WebSocketMessage.model_validate(payload_dict)
            except (json.JSONDecodeError, ValidationError) as exc:
                await manager.send_system_message(websocket, "Error: Invalid or malformed JSON frame — ignored.")
                continue

            if payload.command == "THINK_FEEDBACK":
                await agent.store_feedback(payload.text or "", payload.rating or 0)
                continue

            if payload.command != "THINK":
                await manager.send_system_message(websocket, f"Unknown command '{payload.command}' — ignored.")
                continue

            user_msg    = (payload.text or "").strip()
            engine      = (payload.engine or "LOCAL").upper()
            image_data  = payload.image_data
            
            # Determine approval from server state
            approved = agent.check_and_consume_approval(user_msg)
            
            if not user_msg:
                continue

            if approved:
                try:
                    tool_call = json.loads(user_msg)
                    if "tool" in tool_call:
                        t_name = tool_call["tool"]
                        t_args = tool_call.get("args", {})
                        t_args["_approved"] = True
                        res = await agent.execute_plugin_async(t_name, t_args)
                        
                        await manager.send_state(websocket, "idle")
                        if isinstance(res, str) and res.startswith("SCREENSHOT_BASE64:"):
                            img_b64 = res[len("SCREENSHOT_BASE64:"):]
                            await manager.safe_send_json(websocket, {"type": "chat", "data": f"[EXECUTED] Screenshot captured."})
                            await agent._append_history("user", "SYSTEM: Screenshot captured. Describe what you see.", f"data:image/png;base64,{img_b64}")
                        else:
                            await manager.safe_send_json(websocket, {"type": "chat", "data": f"[EXECUTED]\n{res}"})
                            await agent._append_history("user", f"SYSTEM: User approved '{t_name}'. Result:\n{res}")
                        continue
                except Exception as e:
                    logger.error(f"Failed direct execution of approved tool: {e}")

            await manager.send_state(websocket, "thinking")

            route = get_semantic_route(user_msg)
            semantic_success = False
            if route and not image_data:
                try:
                    result = await agent.execute_plugin_async(
                        route,
                        {"command": user_msg, "query": user_msg, "_approved": approved},
                    )
                except Exception as exc:
                    result = f"Error: Local plugin error: {exc}"

                if isinstance(result, str) and (result.startswith("Error") or "STDERR:" in result):
                    logger.warning(f"Semantic route '{route}' failed. Falling back to LLM. Error: {result}")
                elif isinstance(result, str) and result.startswith("__APPROVAL_REQUIRED__:"):
                    await manager.send_state(websocket, "idle")
                    cmd_text = result[len("__APPROVAL_REQUIRED__:"):]
                    agent.request_approval(cmd_text)
                    await manager.safe_send_json(websocket, {"type": "approval_required", "command": cmd_text})
                    semantic_success = True
                else:
                    await manager.send_state(websocket, "idle")
                    await manager.safe_send_json(websocket, {"type": "chat", "data": f"[LOCAL] {result}"})
                    semantic_success = True
            
            if semantic_success:
                continue

            try:
                from backend.core.orchestrator import AgentOrchestrator
                orchestrator = AgentOrchestrator(agent)
                async def text_generator():
                    async for token_piece in orchestrator.route_task_stream(
                        user_msg, engine=engine, image_data=image_data, approved=approved
                    ):
                        if token_piece.startswith('{"type":'):
                            try:
                                pkt = json.loads(token_piece)
                                await manager.safe_send_json(websocket, pkt)
                                continue
                            except: pass
                        await manager.safe_send_text(websocket, token_piece)
                        yield token_piece

                async for audio_chunk in stream_neural_tts(text_generator()):
                    await manager.safe_send_bytes(websocket, audio_chunk)

                await manager.safe_send_json(websocket, {"type": "stream_end"})
            except Exception as exc:
                logger.error(f"Orchestrator stream error: {exc}")
                await manager.safe_send_json(websocket, {"type": "chat", "data": f"[ERROR] Inference error: {exc}"})

            await manager.send_state(websocket, "idle")

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Unify architecture: Serve the static frontend from the FastAPI backend root.
from fastapi.staticfiles import StaticFiles
import os

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
