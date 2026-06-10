export class UIController {
    constructor() {
        this.statusEl = document.getElementById('conn-text');
        this.chatBox = document.getElementById('chat-history');
        this.inputField = document.getElementById('text-input');
        
        // Setup Telemetry Canvases
        this.cpuCanvas = document.getElementById('cpu-canvas');
        this.ramCanvas = document.getElementById('ram-canvas');
        this.cpuCtx = this.cpuCanvas ? this.cpuCanvas.getContext('2d') : null;
        this.ramCtx = this.ramCanvas ? this.ramCanvas.getContext('2d') : null;
        
        this.resizeCanvas();
        window.addEventListener('resize', () => this.resizeCanvas());
        
        this.history = []; // Max 50 points
        this.cpu = 0;
        this.ram = 0;

        // Interactive mouse tracking
        this.setupInteractivity(this.cpuCanvas);
        this.setupInteractivity(this.ramCanvas);
        
        // Global 3D Dashboard Parallax
        document.addEventListener('mousemove', (e) => {
            const x = (e.clientX / window.innerWidth - 0.5) * 4; // Max tilt 2 deg
            const y = (e.clientY / window.innerHeight - 0.5) * -4;
            const dashboard = document.getElementById('dashboard');
            if(dashboard) {
                dashboard.style.setProperty('--tilt-x', `${x}deg`);
                dashboard.style.setProperty('--tilt-y', `${y}deg`);
            }
        });

        requestAnimationFrame(() => this.drawTelemetry());
    }

    setupInteractivity(canvas) {
        if (!canvas) return;
        canvas.mouseX = -1000;
        canvas.addEventListener('mousemove', (e) => {
            const rect = canvas.getBoundingClientRect();
            canvas.mouseX = e.clientX - rect.left;
        });
        canvas.addEventListener('mouseleave', () => {
            canvas.mouseX = -1000;
        });
    }

    resizeCanvas() {
        if (this.cpuCanvas) {
            this.cpuCanvas.width = this.cpuCanvas.parentElement.clientWidth;
            this.cpuCanvas.height = this.cpuCanvas.parentElement.clientHeight;
        }
        if (this.ramCanvas) {
            this.ramCanvas.width = this.ramCanvas.parentElement.clientWidth;
            this.ramCanvas.height = this.ramCanvas.parentElement.clientHeight;
        }
    }

    setStatus(text) {
        if(this.statusEl) this.statusEl.innerText = text;
    }

    scrollToBottom() {
        if (!this.chatBox) return;
        this.chatBox.scrollTop = this.chatBox.scrollHeight;
    }

    appendChat(text, type = "model") {
        if (!this.chatBox) return;
        const msg = document.createElement('div');
        msg.className = `chat-bubble ${type}`;
        
        if (type === 'model' && window.marked) {
            marked.setOptions({ breaks: true, gfm: true });
            const parsed = marked.parse(text);
            msg.innerHTML = `<div class="md-content">${DOMPurify.sanitize(parsed)}</div>`;
            msg.querySelectorAll('pre code').forEach((block) => {
                if (window.hljs) hljs.highlightElement(block);
            });
        } else {
            msg.innerText = text;
        }
        
        this.chatBox.appendChild(msg);
        this.scrollToBottom();
    }

    streamChat(token) {
        if (!this.chatBox) return;
        let lastBubble = this.chatBox.lastElementChild;
        if (!lastBubble || !lastBubble.classList.contains('model') || lastBubble.dataset.finished) {
            lastBubble = document.createElement('div');
            lastBubble.className = `chat-bubble model`;
            lastBubble.dataset.rawText = "";
            this.chatBox.appendChild(lastBubble);
        }
        
        lastBubble.dataset.rawText += token;
        
        if (window.marked) {
            marked.setOptions({ breaks: true, gfm: true });
            const parsed = marked.parse(lastBubble.dataset.rawText);
            lastBubble.innerHTML = `<div class="md-content">${DOMPurify.sanitize(parsed)}<span class="typing-indicator"></span></div>`;
            lastBubble.querySelectorAll('pre code').forEach((block) => {
                if (window.hljs) hljs.highlightElement(block);
            });
        } else {
            lastBubble.innerHTML = lastBubble.dataset.rawText.replace(/\n/g, '<br>') + '<span class="typing-indicator"></span>';
        }
        
        this.scrollToBottom();
    }

    endStream() {
        if (!this.chatBox) return;
        let lastBubble = this.chatBox.lastElementChild;
        if (lastBubble) {
            lastBubble.dataset.finished = "true";
            const indicator = lastBubble.querySelector('.typing-indicator');
            if (indicator) indicator.remove();
        }
    }

    updateTelemetry(cpu, ram) {
        this.cpu = cpu;
        this.ram = ram;
        this.history.push({ cpu, ram });
        if (this.history.length > 50) this.history.shift();
    }

    drawTelemetry() {
        if (this.history.length < 2) {
            requestAnimationFrame(() => this.drawTelemetry());
            return;
        }

        this.drawGraph(this.cpuCanvas, this.cpuCtx, 'cpu', '#00f3ff');
        this.drawGraph(this.ramCanvas, this.ramCtx, 'ram', '#ff0055');

        requestAnimationFrame(() => this.drawTelemetry());
    }

    drawGraph(canvas, ctx, dataKey, color) {
        if (!canvas || !ctx) return;
        
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        const step = w / 50;
        ctx.beginPath();
        
        for (let i = 0; i < this.history.length; i++) {
            const val = this.history[i][dataKey];
            const x = i * step;
            const y = h - (val / 100) * (h - 20) - 10;
            
            // Mouse Parallax Repulsion
            let interactiveY = y;
            if (canvas.mouseX > 0) {
                const dist = Math.max(0, 80 - Math.abs(canvas.mouseX - x));
                interactiveY -= dist * 0.2; // Bend upwards
            }

            if (i === 0) ctx.moveTo(x, interactiveY);
            else ctx.lineTo(x, interactiveY);
        }

        // Pseudo 3D Glassy Line
        ctx.shadowColor = color;
        ctx.shadowBlur = 10;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // Gradient body
        ctx.lineTo(this.history.length * step, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, color + '55'); // 33% opacity
        gradient.addColorStop(1, 'transparent');
        ctx.fillStyle = gradient;
        ctx.fill();
        ctx.shadowBlur = 0;
    }

    showApprovalDialog(command, onApprove, onDeny) {
        // Build a simple DOM modal overlay
        const overlay = document.createElement('div');
        overlay.style.position = 'absolute';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.background = 'rgba(0,0,0,0.8)';
        overlay.style.display = 'flex';
        overlay.style.justifyContent = 'center';
        overlay.style.alignItems = 'center';
        overlay.style.zIndex = '9999';

        const box = document.createElement('div');
        box.style.background = '#111';
        box.style.padding = '20px';
        box.style.border = '1px solid #ff0055';
        box.style.borderRadius = '8px';
        box.style.color = '#fff';
        box.style.textAlign = 'center';

        box.innerHTML = `
            <h3>Execution Requires Approval</h3>
            <p>Optimus wants to run:</p>
            <pre style="background:#000; padding:10px; color:#00f3ff;">${command}</pre>
            <button id="btn-approve" style="margin-right:10px; background:#00f3ff; color:#000; border:none; padding:8px 16px; cursor:pointer;">Approve</button>
            <button id="btn-deny" style="background:#ff0055; color:#fff; border:none; padding:8px 16px; cursor:pointer;">Deny</button>
        `;
        overlay.appendChild(box);
        document.body.appendChild(overlay);

        document.getElementById('btn-approve').onclick = () => {
            document.body.removeChild(overlay);
            onApprove();
        };
        document.getElementById('btn-deny').onclick = () => {
            document.body.removeChild(overlay);
            onDeny();
        };
    }
}
