# Goal Description

Build "Optimus" - a modular, autonomous local AI assistant core written in Python with a sleek, futuristic web-based UI dashboard. The system will feature a plug-and-play architecture for skills, basic local OS execution capabilities, and a real-time conversational interface.

## User Review Required

> [!IMPORTANT]
> The backend will be built using **FastAPI** for robust async support and WebSocket capabilities (needed for real-time logs and chat).
> The UI will be built using HTML, **Tailwind CSS** (via CDN for simplicity), and vanilla JavaScript.
> The backend will have access to execute terminal commands and read/write files. Please ensure you are running this in a safe environment.

## Open Questions

> [!WARNING]
> 1. Do you have a preferred LLM API (like OpenAI, Gemini, or a local model via Ollama) that Optimus should use to generate conversational responses and decide when to use tools? For the initial setup, I will mock the LLM logic or provide a pluggable interface for it.
> 2. Are there specific color schemes you prefer for the "futuristic" look (e.g., sleek dark mode with neon blue/cyan accents)?

## Proposed Changes

### Backend Core

#### [NEW] `backend/main.py`
FastAPI application setup, WebSocket endpoint for real-time chat and logs, and plugin manager initialization.

#### [NEW] `backend/core/plugin_manager.py`
Logic to dynamically load skills/plugins from a `plugins` directory, allowing easy expansion of Optimus's capabilities.

#### [NEW] `backend/core/agent.py`
The orchestration engine that receives user messages, determines which plugins to call, and formats the responses.

### Plugins

#### [NEW] `backend/plugins/system_vitals.py`
Plugin to check CPU and RAM usage (using `psutil`).

#### [NEW] `backend/plugins/terminal.py`
Plugin to safely execute terminal commands (using `subprocess`).

#### [NEW] `backend/plugins/file_system.py`
Plugin to read/write files to the workspace.

### Frontend UI

#### [NEW] `frontend/index.html`
Sleek, minimal, futuristic dashboard. Includes chat interface, system logs panel, and active plugins list.

#### [NEW] `frontend/styles.css`
Custom styles, glowing animations, and glassmorphism effects supplementing Tailwind.

#### [NEW] `frontend/app.js`
WebSocket connection logic, DOM manipulation for chat, and real-time log updates.

## Verification Plan

### Manual Verification
1. Start the FastAPI backend server using `uvicorn backend.main:app --reload`.
2. Use the Antigravity Browser Subagent to open the frontend on localhost.
3. Send a message like "Optimus, check system vitals" and verify the backend logs the request, invokes the plugin, and returns the correct data.
4. Verify the UI aesthetics meet the "sleek, minimal, futuristic" requirement with smooth animations and dynamic components.
