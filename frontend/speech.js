export class SpeechManager extends EventTarget {
    constructor() {
        super();
        this.synth = window.speechSynthesis;
        if (this.synth && this.synth.onvoiceschanged !== undefined) {
            this.synth.onvoiceschanged = () => this.synth.getVoices();
        }
        this.recognition = null;
        this.isListening = false;
        
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = false;
            this.recognition.interimResults = false;
            this.recognition.lang = 'en-US';

            this.recognition.onstart = () => {
                this.isListening = true;
                this.dispatchEvent(new CustomEvent('listening_start'));
            };

            this.recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                this.dispatchEvent(new CustomEvent('transcript', { detail: transcript }));
            };

            this.recognition.onerror = (event) => {
                console.error("Speech Recognition Error", event.error);
                this.isListening = false;
                this.dispatchEvent(new CustomEvent('listening_end'));
            };

            this.recognition.onend = () => {
                this.isListening = false;
                this.dispatchEvent(new CustomEvent('listening_end'));
            };
        } else {
            console.warn("Speech Recognition not supported in this browser.");
        }
    }

    startListening() {
        if (this.recognition && !this.isListening) {
            try {
                this.recognition.start();
            } catch (e) {
                console.error(e);
            }
        }
    }

    stopListening() {
        if (this.recognition && this.isListening) {
            this.recognition.stop();
        }
    }

    speak(text) {
        if (!this.synth) return;
        if (this.synth.speaking) {
            this.synth.cancel();
        }
        
        // Strip out non-spoken elements (e.g. asterisks, code blocks)
        let cleanText = text.replace(/\*/g, '').replace(/```[\s\S]*?```/g, 'Code block omitted.');
        
        // Chunk long text for Firefox and other browsers with utterance limits
        const chunks = cleanText.match(/[\s\S]{1,3000}(?!\S)/g) || [cleanText];
        
        const voices = this.synth.getVoices();
        const preferred = voices.find(v => v.name.includes('Google UK English Male') || v.name.includes('Microsoft Mark'));

        for (const chunk of chunks) {
            const utterance = new SpeechSynthesisUtterance(chunk.trim());
            if (!utterance.text) continue;
            utterance.rate = 1.05;
            utterance.pitch = 0.95;
            if (preferred) utterance.voice = preferred;
            this.synth.speak(utterance);
        }
    }
}
