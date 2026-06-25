class KineticTelemetryDisplay {
    constructor(canvas, isRam = false) {
        this.canvas = canvas;
        this.ctx = canvas ? canvas.getContext('2d') : null;
        this.isRam = isRam;
        this.history = new Array(50).fill(0);
        this.currentValue = 0;
        this.targetValue = 0;
        
        if (this.canvas) {
            this.loop = this.loop.bind(this);
            this.animFrameId = requestAnimationFrame(this.loop);
        }
    }
    
    destroy() {
        if (this.animFrameId) cancelAnimationFrame(this.animFrameId);
    }
    
    update(value) {
        this.targetValue = value;
        this.history.push(value);
        if (this.history.length > 50) this.history.shift();
    }
    
    loop() {
        this.animFrameId = requestAnimationFrame(this.loop);
        if (!this.ctx || !this.canvas) return;
        
        // Lerp
        this.currentValue += (this.targetValue - this.currentValue) * 0.08;
        
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        
        ctx.clearRect(0, 0, w, h);
        
        ctx.strokeStyle = this.isRam ? 'rgba(255, 0, 85, 0.8)' : 'rgba(0, 243, 255, 0.8)';
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.beginPath();
        
        const step = w / 49;
        
        // Exact text overlay for current telemetry
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = '12px monospace';
        const dataKey = this.isRam ? 'RAM' : 'CPU';
        ctx.fillText(`${dataKey}: ${this.targetValue.toFixed(1)}%`, 5, 15);
        
        for (let i = 0; i < 50; i++) {
            const val = this.history[i] || 0;
            // Draw using exact history but lerped current value for the last point
            const displayVal = (i === 49) ? this.currentValue : val;
            const x = i * step;
            const y = h - (displayVal / 100) * (h - 20) - 10;
            
            // Mouse Parallax Repulsion
            let interactiveY = y;
            if (this.canvas.mouseX > 0) {
                const dist = Math.max(0, 80 - Math.abs(this.canvas.mouseX - x));
                interactiveY -= dist * 0.2; // Bend upwards
            }
            
            if (i === 0) ctx.moveTo(x, interactiveY);
            else ctx.lineTo(x, interactiveY);
        }
        
        ctx.stroke();
        
        // Gradient body
        ctx.beginPath();
        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        if (this.isRam) {
            gradient.addColorStop(0, 'rgba(255, 0, 85, 0.2)');
            gradient.addColorStop(1, 'rgba(255, 0, 85, 0)');
        } else {
            gradient.addColorStop(0, 'rgba(0, 243, 255, 0.2)');
            gradient.addColorStop(1, 'rgba(0, 243, 255, 0)');
        }
        ctx.fillStyle = gradient;
        ctx.fill();
        
        // Glowing dot at the end
        const endY = h - (this.currentValue / 100) * (h - 20) - 10;
        ctx.fillStyle = ctx.strokeStyle;
        ctx.beginPath();
        ctx.arc(w - 2, endY, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 10;
        ctx.shadowColor = ctx.strokeStyle;
        ctx.fill();
        ctx.shadowBlur = 0;
    }
}

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
        
        // Interactive mouse tracking
        this.setupInteractivity(this.cpuCanvas);
        this.setupInteractivity(this.ramCanvas);
        
        this.cpuTracker = new KineticTelemetryDisplay(this.cpuCanvas, false);
        this.ramTracker = new KineticTelemetryDisplay(this.ramCanvas, true);
        
        // Panel Toggles
        const toggleL = document.getElementById('toggle-l-btn');
        const toggleR = document.getElementById('toggle-r-btn');
        const dashboard = document.getElementById('dashboard');

        if (toggleL && dashboard) {
            toggleL.addEventListener('click', () => dashboard.classList.toggle('hide-l'));
        }
        if (toggleR && dashboard) {
            toggleR.addEventListener('click', () => dashboard.classList.toggle('hide-r'));
        }

        
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
        msg.className = `msg ${type}`;
        
        if (text.startsWith('[LOCAL]')) {
            msg.className = 'msg system-tool';
            text = text.substring(7).trim();
            msg.innerHTML = `<div class="md-content" style="border-left: 3px solid var(--neon-cyan); padding-left: 10px; background: rgba(0,243,255,0.05);"><strong>TOOL EXECUTION (LOCAL)</strong><br>${DOMPurify.sanitize(text)}</div>`;
        } else if (text.startsWith('[ERROR]')) {
            msg.className = 'msg system-error';
            msg.innerHTML = `<div class="md-content" style="color:#ff0055">${DOMPurify.sanitize(text)}</div>`;
        } else if (text.startsWith('SYSTEM: Tool')) {
            msg.className = 'msg system-tool';
            msg.innerHTML = `<div class="md-content" style="border-left: 3px solid var(--neon-pink); padding-left: 10px; background: rgba(255,0,85,0.05); font-size: 0.85em; color: #ccc;">${DOMPurify.sanitize(text)}</div>`;
        } else if (type === 'model' && window.marked) {
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
            lastBubble.className = `msg model`;
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
            lastBubble.innerHTML = DOMPurify.sanitize(lastBubble.dataset.rawText.replace(/\n/g, '<br>')) + '<span class="typing-indicator"></span>';
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
            
            // Append Feedback Buttons
            const feedbackContainer = document.createElement('div');
            feedbackContainer.className = 'feedback-container';
            feedbackContainer.style.marginTop = '8px';
            feedbackContainer.style.display = 'flex';
            feedbackContainer.style.gap = '8px';
            
            feedbackContainer.innerHTML = `
                <button class="feedback-btn" onclick="window.sendFeedback(1, this)" style="background:transparent; border:1px solid var(--neon-cyan); border-radius:4px; color:var(--neon-cyan); cursor:pointer; padding:2px 6px; font-size:12px;">👍</button>
                <button class="feedback-btn" onclick="window.sendFeedback(-1, this)" style="background:transparent; border:1px solid var(--neon-pink); border-radius:4px; color:var(--neon-pink); cursor:pointer; padding:2px 6px; font-size:12px;">👎</button>
            `;
            lastBubble.appendChild(feedbackContainer);
        }
    }

    updateMetrics(cpu, ram) {
        if (this.cpuTracker) this.cpuTracker.update(cpu);
        if (this.ramTracker) this.ramTracker.update(ram);
        
        // Update DOM text fields directly
        const cpuText = document.getElementById('cpu-text');
        const ramText = document.getElementById('ram-text');
        
        if (cpuText) {
            cpuText.innerText = `${cpu.toFixed(1)}%`;
            cpuText.style.color = cpu > 90 ? '#ff0055' : '';
        }
        if (ramText) {
            ramText.innerText = `${ram.toFixed(1)}%`;
            ramText.style.color = ram > 90 ? '#ff0055' : '';
        }
    }
    
    // Backwards compatibility alias for existing network code
    updateTelemetry(cpu, ram, disk = 0, net_up = 0, net_down = 0) {
        this.updateMetrics(cpu, ram);
        const diskText = document.getElementById('disk-text');
        const netText = document.getElementById('net-text');
        if (diskText) {
            diskText.innerText = `${disk.toFixed(1)}%`;
            diskText.style.color = disk > 90 ? '#ff0055' : '';
        }
        if (netText) {
            netText.innerText = `${net_up.toFixed(2)} / ${net_down.toFixed(2)}`;
        }
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
            <pre style="background:#000; padding:10px; color:#00f3ff; text-align:left; overflow-x:auto;">${DOMPurify.sanitize(command)}</pre>
            <button class="btn-approve" style="margin-right:10px; background:#00f3ff; color:#000; border:none; padding:8px 16px; cursor:pointer;">Approve</button>
            <button class="btn-deny" style="background:#ff0055; color:#fff; border:none; padding:8px 16px; cursor:pointer;">Deny</button>
        `;
        overlay.appendChild(box);
        document.body.appendChild(overlay);

        box.querySelector('.btn-approve').onclick = () => {
            document.body.removeChild(overlay);
            onApprove();
        };
        box.querySelector('.btn-deny').onclick = () => {
            document.body.removeChild(overlay);
            onDeny();
        };
    }

    showToast(message, type = "info") {
        const toast = document.createElement('div');
        toast.className = `toast-notification ${type}`;
        toast.innerText = message;
        document.body.appendChild(toast);
        
        // Trigger reflow for animation
        void toast.offsetWidth;
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-20px)';
            setTimeout(() => {
                if (toast.parentNode) document.body.removeChild(toast);
            }, 300);
        }, 3000);
    }

    /**
     * Cleans up animation loops
     */
    destroy() {
        if (this._animFrameId) cancelAnimationFrame(this._animFrameId);
        if (this.cpuTracker) this.cpuTracker.destroy();
        if (this.ramTracker) this.ramTracker.destroy();
    }
}
