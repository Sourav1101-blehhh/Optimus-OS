<div align="center">

# ⚡ OPTIMUS OS

### *A next-generation, AI-powered desktop environment with a neural-link interface*

[![License: MIT](https://img.shields.io/badge/License-MIT-cyan.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen)]()

> *"Not just an assistant. An operating intelligence."*

</div>

---

## 🧠 What is Optimus OS?

**Optimus OS** is a self-hosted, AI-driven desktop environment that replaces the traditional GUI with an immersive, cyberpunk-inspired **neural-link interface**. Talk to your computer in natural language, control apps, browse emails, manage your calendar, run code, and monitor your system in real time — all through a single, beautiful glass-morphic dashboard.

It runs **entirely on your machine**, with no subscriptions and no cloud dependency (unless you want one).

---

## ✨ Features

### 🎨 Interface
- **Glass-morphic cyberpunk UI** — animated scanlines, neon accents, dark-mode by default
- **3D CSS parallax dashboard** — the UI subtly reacts to your mouse movements
- **Real-time telemetry** — live CPU, RAM, and GPU usage visualized as canvas waveforms
- **WebGL cognitive core** — animated Three.js neural sphere at the center of the dashboard
- **Drag-and-drop image analysis** — drop any image onto the UI for AI-powered visual analysis

### 🤖 AI Core
- **Local-first** via [Ollama](https://ollama.ai) — no internet required for AI
- **Cloud fallback** — switch to **Google Gemini** or **DeepSeek** in one click
- **Streaming responses** — tokens appear in real time, character by character
- **Long-term memory** — ChromaDB vector database retains and recalls past conversations

### 🎙️ Voice
- **Offline wake-word detection** — say *"Hey Optimus"* and the system activates
- **Speech-to-text input** — hands-free command entry
- **Text-to-speech output** — Optimus speaks its responses back to you

### 🔌 Plugin System (19 built-in plugins)

| Plugin | What it does |
|--------|-------------|
| `app_launcher` | Open, close, and focus any installed application |
| `web_search` | Search the web via DuckDuckGo |
| `browser` | Navigate to URLs and interact with the web |
| `file_system` | Read, write, list and manage your files |
| `terminal` | Run shell commands safely with approval prompts |
| `code_runner` | Execute Python snippets inline |
| `screenshot` | Capture your screen and analyze it with AI |
| `media_control` | Play, pause, skip tracks, adjust volume |
| `google_mail` | Read and summarize unread emails |
| `google_calendar` | View and create calendar events |
| `desktop_automation` | Control the mouse and keyboard |
| `window_manager` | List, switch, and manage open windows |
| `clipboard` | Read from and write to the clipboard |
| `memory` | Store and recall notes and facts |
| `scheduler` | Schedule recurring tasks and reminders |
| `system_vitals` | Monitor CPU, RAM, GPU and battery |
| `smart_home` | Control smart-home devices |
| `weather` | Get live weather for any location |
| `email_reader` | IMAP email reader |

### 🔐 Security
- **HMAC-SHA256** master password — never stored in plain text
- **WebSocket auth handshake** — connections are rejected without a valid token
- **Approval prompts** — destructive terminal/automation commands require explicit confirmation
- **`.gitignore` enforced** — `.env`, memory databases, and caches are never committed

---

## 🚀 Getting Started

### Prerequisites

| Tool | Purpose | Link |
|------|---------|------|
| Python 3.10+ | Backend runtime | [python.org](https://python.org) |
| Ollama | Local AI inference | [ollama.ai](https://ollama.ai) |
| Git | Version control | [git-scm.com](https://git-scm.com) |

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/Optimus-OS.git
cd Optimus-OS
```

### 2. Set up the environment

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

### 3. Configure your secrets

Create a `.env` file in the root directory (never commit this!):

```env
# Required — your master password for the web interface
OPTIMUS_MASTER_PASSWORD=your_secure_password_here

# Optional — for cloud AI back-ends
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key

# Optional — for email & calendar plugins
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

### 4. Pull a local AI model (optional but recommended)

```bash
ollama pull llama3
```

### 5. Start Optimus

**Terminal 1 — Backend:**
```bash
python -m uvicorn backend.main:app --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
python -m http.server 8080
```

### 6. Open the interface

Navigate to **[http://127.0.0.1:8080](http://127.0.0.1:8080)** in your browser and enter your master password.

---

## 🏗️ Project Structure

```
Optimus-OS/
├── backend/
│   ├── core/
│   │   ├── agent.py           # AI orchestration & memory
│   │   ├── audio_engine.py    # Wake-word & TTS
│   │   ├── plugin_manager.py  # Plugin registry
│   │   └── scheduler.py       # Proactive task scheduler
│   ├── plugins/               # 19 capability modules
│   ├── utils/
│   │   └── google_auth.py     # OAuth2 helper
│   └── main.py                # FastAPI server & WebSocket gateway
├── frontend/
│   ├── index.html             # Dashboard layout
│   ├── styles.css             # Cyberpunk design system
│   ├── main.js                # App entry point
│   ├── network.js             # WebSocket lifecycle
│   ├── ui_controller.js       # UI updates & telemetry rendering
│   ├── webgl_core.js          # Three.js neural sphere
│   └── speech.js              # Voice input / output
├── model/                     # Vosk offline wake-word model
├── data/                      # Persistent cron jobs
├── infra/
│   └── nginx.conf             # Optional reverse-proxy config
├── .env.example               # Template for secrets
├── .gitignore
├── LICENSE
├── requirements.txt
└── README.md
```

---

## 🌐 AI Engine Selection

Switch between AI backends from the dropdown in the top-right corner of the UI:

| Engine | Provider | Requires |
|--------|----------|---------|
| **LOCAL** | Ollama (default) | Ollama running locally |
| **GEMINI** | Google | `GEMINI_API_KEY` in `.env` |
| **DEEPSEEK** | DeepSeek/OpenAI API | `OPENAI_API_KEY` in `.env` |

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-plugin`)
3. Commit your changes (`git commit -m 'Add amazing plugin'`)
4. Push the branch (`git push origin feature/amazing-plugin`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ by a human who wanted their computer to think.**

*Star ⭐ this repo if Optimus blew your mind.*

</div>
