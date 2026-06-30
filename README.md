# 🤖 Optimus OS

> **A fully local, autonomous AI assistant for Windows — powered by local LLMs, real-time voice, live web access, and a native WebGL UI.**

Optimus is a self-hosted AI operating system inspired by J.A.R.V.I.S. It runs entirely on your machine, connects to the internet for live data, and can control your PC — launching apps, managing files, running code, controlling media, reading your screen, and much more — all through natural language.

---

## ✨ Features

### 🧠 Multi-Engine AI Brain
- **Local LLM (Ollama):** Powered by `qwen2.5-coder:7b` (or `llava` for vision tasks) running fully offline via Ollama. No data ever leaves your machine by default.
- **Gemini Flash Fallback:** If Ollama is unavailable, Optimus automatically falls back to Google Gemini via the `google-genai` SDK.
- **GPT-4o Support:** Optional OpenAI GPT-4o integration with elevated reasoning effort for debugging tasks.
- **Multi-modal Vision:** Send screenshots or images directly to the AI using the `llava` model for visual analysis.

### ⚡ Zero-Latency Semantic Router
Before passing any command to the LLM, Optimus runs a blazing-fast word-boundary regex intent router. System commands like `open`, `mute`, `volume`, `brightness`, and `screenshot` bypass the AI entirely and execute in milliseconds with no LLM overhead.

### 🔌 21 Native OS Plugins
Every plugin is a self-contained Python module that auto-discovers on startup:

| Plugin | Capability |
|---|---|
| `app_launcher` | Launch any Windows app by name |
| `media_control` | Mute/unmute/play/pause/next/prev (kernel-level ctypes) |
| `web_search` | Live DuckDuckGo + Wikipedia search |
| `terminal` | Run shell commands in WSL2/PowerShell |
| `file_system` | Read, write, list, delete, move files |
| `code_runner` | Execute Python/JS/Bash code in a sandbox |
| `screenshot` | Capture and analyse the screen |
| `screen_reader` | Read text from any region of the screen |
| `desktop_automation` | PyAutoGUI macro sequences |
| `window_manager` | Focus, resize, tile windows |
| `system_vitals` | CPU, RAM, GPU, disk telemetry |
| `clipboard` | Read/write the clipboard |
| `browser` | Open URLs in the default browser |
| `memory` | Persistent semantic memory (ChromaDB) |
| `scheduler` | Schedule tasks (APScheduler) |
| `notifications` | Send Windows toast notifications |
| `weather` | Live weather data |
| `google_calendar` | Read/create Google Calendar events |
| `google_mail` | Read Gmail inbox |
| `email_reader` | Generic IMAP email reader |
| `smart_home` | IoT/smart home device control |

### 🎙️ Wake Word + Voice
- Offline wake-word detection using **Vosk** (`Hey Optimus`)
- Neural TTS voice output using **Kokoro-ONNX** for near-human speech synthesis
- Real-time PCM audio streamed directly over WebSocket as binary float32 frames

### 🌐 Stunning WebGL Interface
- Full **Three.js WebGL** animated orb that pulses in real-time with the AI's token-per-second rate
- **Markdown rendering** with `marked.js` and code syntax highlighting via `highlight.js`
- **DOMPurify** XSS sanitisation on all rendered content
- Glassmorphism dark UI with neon colour palette
- Progressive Web App (PWA) with offline manifest and service worker

### 🔐 Security
- **HMAC-SHA256** password gateway on every WebSocket connection
- Auth token cached in `sessionStorage` (never stored on disk)
- WebSocket rate limiting: 10 messages / 5 seconds per connection
- Per-connection agent isolation — no shared conversation state between users
- Maximum payload size enforcement (1 MB)
- WSL2 sandboxed code execution

### 🧩 Advanced Agent Architecture
- **Dual-tier semantic cache** per agent instance:
  - Tier 0: Exact SHA-256 bitmask O(1) lookup
  - Tier 1: Tri-gram Jaccard similarity (85% threshold)
- **Autonomous tool-use loop** with up to 5 recursive tool invocations
- **Ring-buffer conversation history** (fully isolated per connection)
- Proactive telemetry daemon pushing CPU/RAM at 1 Hz

---

## 🛠️ Setup

### Prerequisites
- **Windows 10/11** (64-bit)
- **Python 3.11+**
- **[Ollama](https://ollama.com/)** installed and running

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/Optimus.git
cd Optimus
```

### 2. Create a Virtual Environment & Install Dependencies
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Pull the Local LLM Model
```bash
ollama pull qwen2.5-coder:7b
# Optional: for vision support
ollama pull llava
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```env
OPTIMUS_MASTER_PASSWORD=your_master_password
GEMINI_API_KEY=your_gemini_api_key        # Optional fallback
OPENAI_API_KEY=your_openai_api_key        # Optional GPT-4o
DEEPSEEK_API_KEY=your_deepseek_api_key    # Optional fallback
ANTHROPIC_API_KEY=your_anthropic_api_key  # Optional fallback
OLLAMA_API_URL=http://127.0.0.1:11434      # Optional Ollama host override
```

If you want Gmail/Calendar support, place `credentials.json` in the repo root and authorize via Google OAuth on first use.

### 5. Download the Vosk speech model
```bash
python download_vendor.py
```

### 6. (Optional) Set Up Kokoro-ONNX TTS
Download the model files from [Kokoro-ONNX](https://github.com/thewh1teagle/kokoro-onnx) and place them in the `model/` directory:
```
model/
  kokoro.onnx
  voices.json
```

### 7. Run Optimus
```bash
python run_headless.py
```
After starting the server, look at your terminal output for the secure dashboard URL. Because Optimus uses a Zero-Trust architecture, a randomized cryptographic token is required to access the dashboard. 

You can access it in two ways:
1. Click the **Optimus icon** in your Windows System Tray and select **Open Dashboard**.
2. **CTRL+Click** the secure URL printed directly in your terminal (e.g., `http://127.0.0.1:8000/?token=...`).

---

## 🏗️ Architecture

```
Optimus/
├── backend/
│   ├── main.py              # FastAPI gateway, WebSocket handler, semantic router
│   ├── core/
│   │   ├── agent.py         # AI orchestrator, LLM streaming, tool-use loop
│   │   ├── audio_engine.py  # Kokoro-ONNX TTS, PCM streaming
│   │   ├── plugin_manager.py# Auto-discovery and async plugin execution
│   │   └── scheduler.py     # APScheduler proactive task daemon
│   └── plugins/             # 21 self-contained OS capability plugins
│
├── frontend/
│   ├── index.html           # PWA shell
│   ├── main.js              # App entrypoint, event orchestration
│   ├── network.js           # WebSocket manager, exponential backoff reconnect
│   ├── ui_controller.js     # Chat rendering, markdown, syntax highlighting
│   ├── webgl_core.js        # Three.js animated orb, TPS-driven amplitude
│   ├── speech.js            # Web Speech API recognition
│   └── styles.css           # Glassmorphism dark UI, neon design system
│
├── model/                   # Kokoro-ONNX TTS model files
├── data/                    # Persistent memory, chroma vector store
└── run_headless.py          # Entry point (Uvicorn server launcher)
```

### Request Lifecycle
```
User speaks / types
    ↓
Vosk wake word detection (offline)
    ↓
WebSocket → FastAPI gateway (HMAC auth)
    ↓
Zero-latency Semantic Router
    ↓ (fast path)              ↓ (LLM path)
Direct Plugin Execution    OptimusAgent.process_message_stream()
    ↓                               ↓
Instant result              Dual-tier semantic cache check
                                    ↓ (miss)
                            Ollama qwen2.5-coder:7b streaming
                                    ↓ (on error)
                            Gemini Flash fallback
                                    ↓
                            JSON tool-call extraction
                                    ↓ (if tool detected)
                            Autonomous tool-use loop (max 5)
                                    ↓
Kokoro-ONNX TTS → PCM binary frames over WebSocket
    ↓
Browser AudioContext plays response
WebGL orb pulses at token rate
```

---

## 💬 Example Commands

```
"Open Spotify"
"Mute the system volume"
"Search the web for the population of India"
"Take a screenshot and describe what you see"
"Run this Python script: print('Hello World')"
"What files are in my Downloads folder?"
"Set a reminder for 6pm to call mom"
"What's the weather like in Mumbai?"
"Read my latest emails"
"Open YouTube in the browser"
"Increase the volume by 20%"
"What's my CPU and RAM usage?"
```

---

## 🧪 Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11, FastAPI, Uvicorn, asyncio |
| **AI Inference** | Ollama (local), Google Gemini Flash, OpenAI GPT-4o |
| **Local LLM** | qwen2.5-coder:7b, llava (vision) |
| **TTS** | Kokoro-ONNX |
| **Wake Word** | Vosk |
| **Vector Memory** | ChromaDB |
| **Task Scheduling** | APScheduler |
| **OS Automation** | ctypes (Win32 API), subprocess, pyautogui |
| **Frontend** | Vanilla HTML/CSS/JS, Three.js, marked.js, highlight.js |
| **Security** | HMAC-SHA256, DOMPurify |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <strong>Built with ❤️ as a fully local, privacy-first AI assistant.</strong><br>
  <em>No cloud required. Everything runs on your machine.</em>
</div>
