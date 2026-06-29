/**
 * network.js — Optimus OS Frontend Network Manager v5.0
 * ======================================================
 *
 * Architecture: EventTarget-based Event Bus
 * Security:     Persistent token caching in sessionStorage
 * Reliability:  Exponential backoff auto-reconnect (max 30 s interval)
 *
 * Reconnection Protocol:
 *   On unexpected WebSocket disconnect, the NetworkManager automatically
 *   attempts to re-establish the connection using exponential backoff:
 *     Attempt 1:  1 s delay
 *     Attempt 2:  2 s delay
 *     Attempt 3:  4 s delay
 *     Attempt 4:  8 s delay
 *     Attempt 5+: 30 s delay (cap)
 *
 *   The active security token is cached in sessionStorage under the key
 *   'optimus_session_token' so the user is never prompted again after the
 *   initial login — not even after a page reload.  Manual logout (or
 *   clearing site data) is required to force re-authentication.
 *
 *   UI state (chat history, telemetry) is preserved across reconnects
 *   because the event listeners live in main.js independently of the
 *   WebSocket connection lifecycle.
 *
 * Token-Per-Second (TPS) Metering:
 *   A 500 ms sliding window counts incoming raw token frames.  The smoothed
 *   TPS value is exponentially decayed at 16 ms intervals and dispatched as
 *   an 'amplitude' event for the WebGL shader to consume.
 */
export class NetworkManager extends EventTarget {
    /**
     * @param {string} wsUrl - The WebSocket URL to connect to (ws://host:port/ws)
     */
    constructor(wsUrl) {
        super();

        this.wsUrl     = wsUrl;
        this.ws        = null;
        this.token     = null;

        // Exponential backoff state
        this._reconnectAttempt  = 0;
        this._reconnectTimer    = null;
        this._intentionalClose  = false; // Prevents reconnect on explicit disconnect()

        // TPS metering state
        this._tvCount       = 0;
        this._tvWindowStart = performance.now();
        this._tvWindowMs    = 500;
        this._smoothTps     = 0;
        this._satTps        = 28.0;  // Saturation point (amplitude = 1.0 at this TPS)

        // Internal tick loops — run continuously regardless of connection state
        this._tickInterval  = setInterval(() => this._tick(), 500);
        this._decayInterval = setInterval(() => this._decay(), 16);
    }

    // -----------------------------------------------------------------------
    // Connection Management
    // -----------------------------------------------------------------------

    /**
     * Initiates the WebSocket connection and stores the token in sessionStorage.
     * This is the only entry point for establishing a connection.
     *
     * @param {string} token - The master password string (persisted to sessionStorage as a hash)
     */
    async connect(token) {
        if (token.length === 64 && /^[0-9a-f]{64}$/i.test(token)) {
            this.token = token;
        } else {
            const encoder = new TextEncoder();
            const data = encoder.encode(token);
            const hashBuffer = await crypto.subtle.digest('SHA-256', data);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
            this.token = hashHex;
        }
        sessionStorage.setItem('optimus_session_token', this.token);
        this._intentionalClose = false;
        this._openSocket();
    }

    /**
     * Creates and configures a new WebSocket instance, wiring all event
     * handlers.  Called both on initial connect() and on each reconnect attempt.
     *
     * @private
     */
    _openSocket() {
        // Clean up any existing socket before creating a new one
        if (this.ws) {
            this.ws.onclose   = null; // Prevent old handler from firing
            this.ws.onerror   = null;
            this.ws.onmessage = null;
            this.ws.onopen    = null;
            if (this.ws.readyState === WebSocket.OPEN ||
                this.ws.readyState === WebSocket.CONNECTING) {
                this.ws.close();
            }
            this.ws = null;
        }

        this.ws = new WebSocket(this.wsUrl);
        this.ws.binaryType = 'arraybuffer'; // ensure binary frames are arraybuffers

        this.ws.onopen = () => {
            // The backend expects {"token": "..."}.
            this.ws.send(JSON.stringify({ token: this.token }));
            this._reconnectAttempt = 0; // Reset backoff on successful connection
            this.dispatchEvent(new CustomEvent('status', { detail: 'Connected' }));

            // Initialize AudioContext on connection
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
                this.nextAudioTime = 0;
            }
        };

        this.ws.onmessage = (event) => {
            if (typeof event.data !== 'string') {
                // Handle binary float32 PCM data
                if (!this.audioContext) return;
                
                const float32Data = new Float32Array(event.data);
                const buffer = this.audioContext.createBuffer(1, float32Data.length, 24000);
                buffer.getChannelData(0).set(float32Data);
                
                const source = this.audioContext.createBufferSource();
                source.buffer = buffer;
                source.connect(this.audioContext.destination);
                
                const currentTime = this.audioContext.currentTime;
                if (this.nextAudioTime < currentTime) {
                    this.nextAudioTime = currentTime;
                }
                source.start(this.nextAudioTime);
                this.nextAudioTime += buffer.duration;
                return;
            }

            let data;
            try {
                data = JSON.parse(event.data);
            } catch (_parseErr) {
                data = null;
            }

            if (data && typeof data === 'object' && data.type) {
                switch (data.type) {
                    case 'telemetry':
                        this.dispatchEvent(new CustomEvent('telemetry', { detail: data }));
                        break;
                    case 'chat':
                        this.dispatchEvent(new CustomEvent('chat', { detail: data.data }));
                        break;
                    case 'state':
                        this.dispatchEvent(new CustomEvent('state', { detail: data.data }));
                        break;
                    case 'approval_required':
                        this.dispatchEvent(new CustomEvent('approval', { detail: data }));
                        break;
                    case 'stream_end':
                        this.dispatchEvent(new CustomEvent('stream_end'));
                        break;
                    case 'tool_depth_exceeded':
                        this.dispatchEvent(new CustomEvent('tool_depth_exceeded', { detail: data.message }));
                        break;
                    case 'rate_limited':
                        const warningDiv = document.createElement('div');
                        warningDiv.style.position = 'fixed';
                        warningDiv.style.top = '20px';
                        warningDiv.style.left = '50%';
                        warningDiv.style.transform = 'translateX(-50%)';
                        warningDiv.style.padding = '15px 30px';
                        warningDiv.style.background = 'rgba(255, 170, 0, 0.9)';
                        warningDiv.style.color = '#000';
                        warningDiv.style.fontWeight = 'bold';
                        warningDiv.style.fontFamily = 'var(--font-cyber), monospace';
                        warningDiv.style.borderRadius = '4px';
                        warningDiv.style.zIndex = '999999';
                        warningDiv.style.boxShadow = '0 0 20px rgba(255, 170, 0, 0.8)';
                        warningDiv.style.border = '2px solid #fff';
                        warningDiv.innerText = data.data || "RATE LIMIT EXCEEDED. PLEASE SLOW DOWN.";
                        document.body.appendChild(warningDiv);
                        setTimeout(() => warningDiv.remove(), 4000);
                        break;
                    case 'log':
                        console.info('[Optimus Backend]', data.data);
                        break;
                    case 'plugins':
                        console.info('[Optimus] Plugins loaded:', data.data);
                        break;
                    default:
                        console.warn('[Optimus] Unknown message type:', data.type);
                }
            } else {
                // Not a structured JSON object — treat as a raw streaming token from LLM
                this._tvCount++;
                this.dispatchEvent(new CustomEvent('token', { detail: event.data }));
            }
        };

        this.ws.onerror = (err) => {
            // Errors are followed by onclose; reconnect logic lives in onclose
            console.error('[Optimus Network] WebSocket error:', err);
        };

        this.ws.onclose = (event) => {
            this.dispatchEvent(new CustomEvent('status', { detail: 'Disconnected' }));

            // Code 1008 = Policy Violation = auth rejected by backend.
            // Retrying with the same bad token would loop forever — instead,
            // wipe the cached token and surface a re-auth prompt to the user.
            if (event.code === 1008) {
                sessionStorage.removeItem('optimus_session_token');
                this.token = null;
                this.dispatchEvent(new CustomEvent('status', {
                    detail: 'Auth failed — password rejected. Please reload to re-enter password.'
                }));
                console.error('[Optimus Network] Auth rejected (1008). Cached token cleared.');
                return; // Do NOT schedule reconnect with a bad token
            }

            if (!this._intentionalClose) {
                // Unexpected disconnect (network drop, server restart, etc.)
                // — begin exponential backoff reconnect with the cached token.
                this._scheduleReconnect();
            }
        };
    }

    /**
     * Schedules the next reconnect attempt using exponential backoff.
     *
     * Delay formula:  min(2^attempt × 1000 ms, 30 000 ms)
     *   Attempt 0: 1 s
     *   Attempt 1: 2 s
     *   Attempt 2: 4 s
     *   Attempt 3: 8 s
     *   Attempt 4: 16 s
     *   Attempt 5+: 30 s  (capped)
     *
     * @private
     */
    _scheduleReconnect() {
        if (this._reconnectTimer !== null) return; // Already scheduled

        const delayMs = Math.min(
            Math.pow(2, this._reconnectAttempt) * 1000,
            30_000
        );
        this._reconnectAttempt++;

        console.info(
            `[Optimus Network] Reconnecting in ${delayMs / 1000}s ` +
            `(attempt ${this._reconnectAttempt})...`
        );
        this.dispatchEvent(new CustomEvent('status', {
            detail: `Reconnecting in ${delayMs / 1000}s…`
        }));

        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;

            // Recover the cached token — no user prompt needed
            const cachedToken = this.token || sessionStorage.getItem('optimus_session_token');
            if (!cachedToken) {
                this.dispatchEvent(new CustomEvent('status', {
                    detail: 'Reconnect failed: no token cached. Please reload.'
                }));
                return;
            }

            this.token = cachedToken;
            this._openSocket();
        }, delayMs);
    }

    /**
     * Gracefully closes the WebSocket connection and suppresses reconnection.
     * Call this when the user explicitly logs out or navigates away.
     */
    disconnect() {
        this._intentionalClose = true;
        if (this._reconnectTimer !== null) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.onclose = null;
            this.ws.onerror = null;
            this.ws.onmessage = null;
            this.ws.onopen = null;
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }
    }

    /**
     * Destroys the NetworkManager instance and clears all interval timers.
     * Call on application teardown to prevent memory leaks.
     */
    destroy() {
        this.disconnect();
        clearInterval(this._tickInterval);
        clearInterval(this._decayInterval);
    }

    // -----------------------------------------------------------------------
    // Outbound Messaging
    // -----------------------------------------------------------------------

    /**
     * Sends a THINK command to the backend.
     *
     * @param {string}      text        - User's input text
     * @param {string}      engine      - Engine key: "LOCAL", "GEMINI", "GPT", etc.
     * @param {string|null} image_data  - Base64 image data URI or null
     * @param {boolean}     approved    - HITL approval flag
     */
    sendThought(text, engine = 'LOCAL', image_data = null, approved = false) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('[Optimus Network] Cannot send: WebSocket not open.');
            return;
        }
        this.ws.send(JSON.stringify({
            command: 'THINK',
            text,
            engine,
            image_data,
            approved,
        }));
    }

    // -----------------------------------------------------------------------
    // TPS Metering (powers WebGL amplitude uniform)
    // -----------------------------------------------------------------------

    /**
     * Called every 500 ms.  Computes the raw TPS from the token count
     * accumulated in the sliding window, then applies exponential smoothing
     * (alpha=0.15) to reduce jitter.
     *
     * @private
     */
    _tick() {
        const now     = performance.now();
        const elapsed = now - this._tvWindowStart;
        if (elapsed >= this._tvWindowMs - 50) { // Tolerate timer imprecision
            const rawTps      = (this._tvCount / elapsed) * 1000;
            this._smoothTps   = 0.15 * rawTps + 0.85 * this._smoothTps;
            this._tvCount     = 0;
            this._tvWindowStart = now;
        }
    }

    /**
     * Called at ~60 fps (every 16 ms).  Applies a multiplicative decay to
     * the smoothed TPS value to make the WebGL orb settle gracefully when
     * token streaming stops.  Dispatches an 'amplitude' event with the
     * smoothstep-transformed [0, 1] amplitude value.
     *
     * Smoothstep transform:  f(t) = t² × (3 − 2t)  produces an S-curve
     * that makes low TPS almost invisible and high TPS very expressive.
     *
     * @private
     */
    _decay() {
        this._smoothTps *= 0.92;
        if (this._smoothTps < 0.01) this._smoothTps = 0;

        const ratio     = Math.min(this._smoothTps / this._satTps, 1.0);
        const amplitude = ratio * ratio * (3 - 2 * ratio); // smoothstep
        this.dispatchEvent(new CustomEvent('amplitude', { detail: amplitude }));
    }

}
