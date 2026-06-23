import { WebGLCore } from './webgl_core.js';
import { NetworkManager } from './network.js';
import { UIController } from './ui_controller.js';
import { SpeechManager } from './speech.js';

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

window.exportConversation = function(e) {
    if (e) e.stopPropagation();
    const chatBox = document.getElementById('chat-history');
    if (!chatBox) return;
    let exportText = "Optimus OS Conversation Export\n==============================\n\n";
    chatBox.querySelectorAll('.chat-bubble').forEach(bubble => {
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
    
    // Connect to WebSocket via NetworkManager
    const wsUrl = `ws://${window.location.hostname || '127.0.0.1'}:8000/ws`;
    network = new NetworkManager(wsUrl);
    network.connect(token);

    // Network Event Binding
    network.addEventListener('status', (e) => {
        ui.setStatus(e.detail);
        if (e.detail === 'Connected') {
            // Hide the login overlay when connected
            document.getElementById('login-overlay').classList.add('hidden');
        } else {
            // If it's a specific auth failure, show the overlay again with an error
            if (e.detail.includes("Auth failed") || e.detail.includes("Unauthorized")) {
                document.getElementById('login-overlay').classList.remove('hidden');
                document.getElementById('login-error').innerText = "AUTH REJECTED. TRY AGAIN.";
                document.getElementById('login-password').value = "";
            }
        }
    });
    
    network.addEventListener('state', (e) => {
        ui.setStatus(`System: ${e.detail}`);
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
        const command = e.detail;
        ui.showApprovalDialog(command, 
            () => { // On Approve
                ui.appendChat(`> User approved execution: ${command}`, 'user');
                network.sendThought(command, "LOCAL", null, true);
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

    // Global functions for inline HTML handlers
    window.sendCommand = (text) => {
        ui.appendChat(text, 'user');
        const engineSelect = document.getElementById('engine-select');
        const engine = engineSelect ? engineSelect.value : "GEMINI";
        network.sendThought(text, engine, null, false);
    };

    window.sendFeedback = (rating, element) => {
        if (!network || !network.ws || network.ws.readyState !== WebSocket.OPEN) {
            ui.showToast("Network offline. Feedback not recorded.", "error");
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
        
        ui.showToast(`Feedback recorded: ${rating > 0 ? 'Positive' : 'Negative'}`);
        
        // Disable buttons after click
        const buttons = bubble.querySelectorAll('.feedback-btn');
        buttons.forEach(b => b.style.display = 'none');
    };

    window.toggleDevice = (element, text) => {
        element.classList.toggle('active');
        window.sendCommand(text);
    };

    window.toggleCommHUD = () => {
        const hud = document.getElementById('comm-hud');
        if (hud) hud.classList.toggle('collapsed');
    };

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
                network.sendThought(text, "LOCAL", null, false);
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
        network.sendThought(text, "GEMINI", null, false);
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
    // Small timeout to allow DOM to settle
    setTimeout(promptForToken, 500);
};
