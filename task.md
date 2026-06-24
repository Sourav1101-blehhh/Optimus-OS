# Tasks

## Phase 1 (Zero-Latency Neural Audio Streaming)
- [x] Install `kokoro-onnx` and `sounddevice`
- [x] Update `backend/core/audio_engine.py` to stream TTS tokens
- [x] Update `backend/main.py` to send binary audio through WebSocket
- [x] Update `frontend/network.js` to play back float32 PCM audio stream


## Phase 2 (Kernel-Level Automation)
- [x] Completely refactor `backend/plugins/window_manager.py` to eliminate PowerShell subprocesses.
- [x] Use Python's `ctypes` (`ctypes.windll.user32`) to interact with native Win32 C-bindings.
- [x] Re-implement `list`, `focus`, `minimize`, and `close` actions using HWNDs, `EnumWindows`, `GetWindowTextW`, `SetForegroundWindow`, `ShowWindow`, and `PostMessage`.

## Phase 4 (Database Concurrency WAL)
- [x] In `backend/core/agent.py`, locate `_get_global_chromadb()`.
- [x] Before initializing `chromadb.PersistentClient`, import `sqlite3` and directly connect to the `chroma.sqlite3` file located inside `c:\Users\KIIT\OneDrive\Desktop\Optimus\chroma_db\`.
- [x] Execute `PRAGMA journal_mode=WAL;` to enable Write-Ahead Logging for high concurrency.
- [x] Ensure this executes safely inside a try/except block before ChromaDB takes over.

## Phase 3 (Secure Sandbox Runtime)
- [x] Refactor `backend/plugins/code_runner.py` to execute Python scripts inside WSL2 (`wsl -e python3`).
- [x] Map the temporary script path to the WSL file system path.
- [x] Make it more secure by adding execution timeouts.

## Phase 5 (Isolated Local PWA Assets)
- [x] Create a `frontend/static/vendor/` directory.
- [x] Download Three.js, Marked.js, DOMPurify, highlight.js into `vendor/` (script created).
- [x] Update `frontend/index.html` to load these local `<script>` tags instead of CDNs.
- [x] Update `frontend/webgl_core.js` to rely on the global `THREE` object instead of importing from Skypack CDN.
- [x] Update `frontend/service-worker.js` cache array to include the new local vendor assets.
