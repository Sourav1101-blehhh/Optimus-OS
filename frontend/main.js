import { WebGLCore } from './webgl_core.js?v=4';
import { NetworkManager } from './network.js?v=4';
import { UIController } from './ui_controller.js?v=4';
import { SpeechManager } from './speech.js?v=4';

let network, webgl, ui, speech;
let accumulatedStream = "";

function promptForToken() {
    const cached = sessionStorage.getItem('optimus_session_token');
    if (cached) {
        initOptimus(cached);
        return;
    }
    const overlay = document.getElementById('login-overlay');
    if (overlay) overlay.classList.remove('hidden');
}

// Global functions for inline HTML handlers
window.sendCommand = (text) => {
    if (!ui || !network) return;
    ui.appendChat(text, 'user');
    const engineSelect = document.getElementById('engine-select');
    const engine = engineSelect ? engineSelect.value : "GEMINI";
    network.sendThought(text, engine, null, false);
};

window.sendFeedback = (rating, element) => {
    if (!network || !network.ws || network.ws.readyState !== WebSocket.OPEN) {
        if (ui) ui.showToast("Network offline. Feedback not recorded.", "error");
        return;
    }
    const bubble = element.closest('.chat-bubble');
    if (!bubble) return;
    const text = bubble.dataset.rawText || bubble.innerText;
    network.ws.send(JSON.stringify({
        command: "THINK_FEEDBACK",
        text: text,
        rating: rating
    }));
    if (ui) ui.showToast(`Feedback recorded: ${rating > 0 ? 'Positive' : 'Negative'}`);
    const buttons = bubble.querySelectorAll('.feedback-btn');
    buttons.forEach(b => b.style.display = 'none');
};

window.toggleDevice = (element, text) => {
    element.classList.toggle('active');
    window.sendCommand(text);
};

window.toggleCommHUD = () => {
    const hud = document.getElementById('comm-hud');
    if (hud) {
        hud.classList.toggle('collapsed');
        const arrow = document.getElementById('toggle-arrow');
        if (arrow) arrow.innerText = hud.classList.contains('collapsed') ? '◀' : '▶';
    }
};

window.exportConversation = function(e) {
    if (e) e.stopPropagation();
    const chatBox = document.getElementById('chat-history');
    if (!chatBox) return;
    let exportText = "Optimus OS Conversation Export\n==============================\n\n";
    chatBox.querySelectorAll('.msg').forEach(bubble => {
        const isUser = bubble.classList.contains('user');
        const role = isUser ? "USER" : "OPTIMUS";
        const content = bubble.innerText.trim();
        if (content) {
            exportText += `[${role}]:\n${content}\n\n`;
        }
    });
    const blob = new Blob([exportText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `optimus_conversation_${new Date().getTime()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

let isInitialized = false;

function initOptimus(token) {
    if (isInitialized) {
        if (network) network.destroy();
        if (ui) ui.destroy();
        if (window._mainAnimFrameId) cancelAnimationFrame(window._mainAnimFrameId);
    }
    isInitialized = true;

    ui = new UIController();
    webgl = new WebGLCore('container', 'cognitive-canvas');
    speech = new SpeechManager();
    
    // Extract boot token from URL or localStorage
    const urlParams = new URLSearchParams(window.location.search);
    let bootToken = urlParams.get('token') || localStorage.getItem('optimus_boot_token');
    
    if (bootToken) {
        localStorage.setItem('optimus_boot_token', bootToken);
        // Clean up URL visually
        if (urlParams.has('token')) {
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    } else {
        document.getElementById('login-error').innerText = "FATAL: Boot token missing! Please launch Optimus from the System Tray.";
        return;
    }

    // Connect to WebSocket via NetworkManager
    let protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let wsUrl = `${protocol}//${window.location.host}/ws`;
    if (bootToken) {
        wsUrl += `?token=${bootToken}`;
    }
    network = new NetworkManager(wsUrl);
    network.connect(token);

    // Network Event Binding
    network.addEventListener('status', (e) => {
        ui.setStatus(e.detail);
        if (e.detail === 'Connected') {
            // Hide the login overlay when connected
            const overlay = document.getElementById('login-overlay');
            if (overlay) overlay.classList.add('hidden');
        } else {
            // If it's a specific auth failure, show the overlay again with an error
            const detailStr = String(e.detail || "");
            if (detailStr.includes("Auth failed") || detailStr.includes("Unauthorized")) {
                const overlay = document.getElementById('login-overlay');
                const error = document.getElementById('login-error');
                const pwd = document.getElementById('login-password');
                if (overlay) overlay.classList.remove('hidden');
                if (error) error.innerText = "AUTH REJECTED. TRY AGAIN.";
                if (pwd) pwd.value = "";
            } else if (detailStr === 'Disconnected') {
                const error = document.getElementById('login-error');
                if (error) error.innerText = "BACKEND OFFLINE. RETRYING...";
            }
        }
    });
    
    network.addEventListener('state', (e) => {
        ui.setStatus(`System: ${e.detail}`);
        if (webgl) webgl.setAIState(String(e.detail).toUpperCase());
    });

    network.addEventListener('telemetry', (e) => {
        ui.updateTelemetry(e.detail.cpu, e.detail.ram, e.detail.disk, e.detail.net_up, e.detail.net_down);
    });

    network.addEventListener('amplitude', (e) => {
        webgl.setTelemetry(e.detail);
    });

    network.addEventListener('chat', (e) => {
        ui.appendChat(e.detail, 'model');
        speech.speak(e.detail);
    });

    network.addEventListener('vision_intercept', (e) => {
        const data = e.detail;
        const overlay = document.getElementById('vision-overlay');
        const box = document.getElementById('vision-box');
        
        if (overlay && box) {
            // Draw box
            box.style.left = data.x + 'px';
            box.style.top = data.y + 'px';
            box.style.width = data.w + 'px';
            box.style.height = data.h + 'px';
            
            // Show overlay
            overlay.classList.remove('hidden');
            
            // Handlers
            document.getElementById('vision-allow-btn').onclick = () => {
                overlay.classList.add('hidden');
                network.ws.send(JSON.stringify({ command: 'APPROVE', token: `VISION_${data.x}_${data.y}` }));
            };
            
            document.getElementById('vision-deny-btn').onclick = () => {
                overlay.classList.add('hidden');
                network.ws.send(JSON.stringify({ command: 'DENY', token: `VISION_${data.x}_${data.y}` }));
            };
        }
    });

    network.addEventListener('token', (e) => {
        accumulatedStream += e.detail;
        ui.streamChat(e.detail);
    });

    network.addEventListener('stream_end', () => {
        ui.endStream();
        speech.speak(accumulatedStream);
        accumulatedStream = "";
    });

    network.addEventListener('approval', (e) => {
        const data = e.detail;
        const displayCommand = data.command;
        const payloadStr = data.payload || data.command;
        
        ui.showApprovalDialog(displayCommand, 
            () => { // On Approve
                ui.appendChat(`> User approved execution: ${displayCommand}`, 'user');
                network.sendThought(payloadStr, "LOCAL", null, true);
            },
            () => { // On Deny
                ui.appendChat("> User denied execution.", 'user');
            }
        );
    });

    network.addEventListener('tool_depth_exceeded', (e) => {
        // Structured warning from the v5 depth guard — surface it visibly in the UI
        ui.appendChat(
            `⚠️ DEPTH LIMIT: ${e.detail}`,
            'model'
        );
    });


    // UI Input Binding
    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const text = ui.inputField.value.trim();
            const engineSelect = document.getElementById('engine-select');
            const engine = engineSelect ? engineSelect.value : "GEMINI";
            if (text) {
                ui.appendChat(text, 'user');
                network.sendThought(text, engine, null, false);
                ui.inputField.value = '';
            }
        });
    }

    const terminalForm = document.getElementById('terminal-input-form');
    const terminalInput = document.getElementById('terminal-text-input');
    if (terminalForm && terminalInput) {
        terminalForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const text = terminalInput.value.trim();
            if (text) {
                ui.appendChat(`> ${text}`, 'user');
                const engineSelect = document.getElementById('engine-select');
                const engine = engineSelect ? engineSelect.value : "LOCAL";
                network.sendThought(text, engine, null, false);
                terminalInput.value = '';
            }
        });
    }

    // Speech UI Binding
    const micBtn = document.getElementById('mic-btn');
    if (micBtn) {
        micBtn.addEventListener('click', () => {
            if (speech.isListening) speech.stopListening();
            else speech.startListening();
        });
    }

    speech.addEventListener('listening_start', () => {
        if(micBtn) micBtn.classList.add('recording');
        ui.setStatus('Listening...');
    });

    speech.addEventListener('listening_end', () => {
        if(micBtn) micBtn.classList.remove('recording');
        ui.setStatus('Idle');
    });

    speech.addEventListener('transcript', (e) => {
        const text = e.detail;
        ui.appendChat(text, 'user');
        const engineSelect = document.getElementById('engine-select');
        const engine = engineSelect ? engineSelect.value : "GEMINI";
        network.sendThought(text, engine, null, false);
    });

    // Start Render Loop
    function render(time) {
        webgl.render(time);
        window._mainAnimFrameId = requestAnimationFrame(render);
    }
    window._mainAnimFrameId = requestAnimationFrame(render);
}

// Start
window.onload = () => {
    document.getElementById('login-btn').addEventListener('click', () => {
        const pwdInput = document.getElementById('login-password');
        const pwd = pwdInput.value.trim();
        if (pwd) {
            document.getElementById('login-error').innerText = "CONNECTING...";
            initOptimus(pwd);
        } else {
            document.getElementById('login-error').innerText = "Please enter a key.";
        }
    });

    document.getElementById('login-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('login-btn').click();
        }
    });

    // Small timeout to allow DOM to settle
    setTimeout(promptForToken, 500);
};
