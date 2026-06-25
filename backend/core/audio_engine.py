"""
audio_engine.py — Optimus Offline Wake-Word & TTS Gateway v5.0
==============================================================
Provides independent, low-latency background audio processing.

1. WAKE WORD:
   Continuously monitors the default microphone in a separate thread.
   Uses Vosk (true offline, free) or PyPorcupine (if Picovoice key is set).
   When "hey optimus" is detected, it pushes an event to a thread-safe
   asyncio.Queue that the main FastAPI app consumes to trigger client focus.

2. NEURAL TTS:
   Exposes an interface to generate TTS using a high-quality local engine.
   (Designed for kokoro-onnx, defaulting to a fast simulated byte-stream
   fallback if the heavy weights aren't present).
"""
import asyncio
import json
import logging
import os
import queue
import sys
import threading
from typing import AsyncGenerator

import numpy as np
import sounddevice as sd

logger = logging.getLogger("OptimusAudio")

# Event queue to communicate wake-word detections back to the main async loop
WAKE_EVENT_QUEUE = None

def get_wake_queue() -> asyncio.Queue:
    global WAKE_EVENT_QUEUE
    if WAKE_EVENT_QUEUE is None:
        loop = asyncio.get_running_loop()
        WAKE_EVENT_QUEUE = asyncio.Queue()
    return WAKE_EVENT_QUEUE

# --- TTS Subsystem ---

import re

kokoro_model = None
kokoro_available = False
try:
    from kokoro_onnx import Kokoro
    # Try loading the model if it exists
    model_path = os.path.join(os.path.dirname(__file__), "..", "..", "model", "kokoro.onnx")
    voices_path = os.path.join(os.path.dirname(__file__), "..", "..", "model", "voices.json")
    if os.path.exists(model_path) and os.path.exists(voices_path):
        kokoro_model = Kokoro(model_path, voices_path)
        kokoro_available = True
        logger.info("Kokoro-ONNX model loaded successfully.")
    else:
        logger.warning("Kokoro-ONNX model files not found. Using TTS fallback.")
except ImportError:
    logger.warning("kokoro_onnx not installed. Using TTS fallback.")

async def text_processor(text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    buffer = ""
    async for token in text_stream:
        buffer += token
        # Split by sentence boundaries (. ! ? \n)
        parts = re.split(r'([.!?\n]+)', buffer)
        
        # If there are multiple parts, yield the complete sentences
        if len(parts) > 1:
            for i in range(0, len(parts) - 1, 2):
                sentence = parts[i] + parts[i+1]
                sentence = sentence.strip()
                if sentence:
                    yield sentence
            buffer = parts[-1]
            
    if buffer.strip():
        yield buffer.strip()

async def stream_neural_tts(text_stream: AsyncGenerator[str, None]) -> AsyncGenerator[bytes, None]:
    """
    Streams near-human phonemes chunk-by-chunk under 50ms latency.
    Yields float32 PCM binary arrays.
    """
    async for sentence in text_processor(text_stream):
        if not sentence:
            continue
            
        logger.info(f"TTS Engine synthesizing: {sentence[:30]}...")
        
        if kokoro_available and kokoro_model is not None:
            try:
                # kokoro_model.create_stream yields chunks as numpy arrays
                stream = kokoro_model.create_stream(sentence, voice="af_heart")
                # Handle both async and sync generator from kokoro
                if hasattr(stream, '__aiter__'):
                    async for chunk in stream:
                        yield chunk.tobytes()
                else:
                    for chunk in stream:
                        yield chunk.tobytes()
                        await asyncio.sleep(0.001)
                continue
            except Exception as e:
                logger.error(f"Kokoro stream failed: {e}")
                # Fallthrough to fallback
        
        # Fallback simulation
        sample_rate = 24000
        duration_ms = 100
        samples_per_chunk = int(sample_rate * (duration_ms / 1000.0))
        
        await asyncio.sleep(0.05)
        
        for _ in range(5):
            chunk = np.zeros(samples_per_chunk, dtype=np.float32)
            yield chunk.tobytes()
            await asyncio.sleep(0.1)

# --- Wake-Word Subsystem ---
class WakeWordDaemon:
    def __init__(self):
        self._running = False
        self._thread = None
        self._q = queue.Queue()
        self.model = None

    def _init_vosk(self):
        try:
            from vosk import Model, KaldiRecognizer
            # Requires a lightweight Vosk model downloaded in 'model' dir
            # https://alphacephei.com/vosk/models (e.g. vosk-model-small-en-us)
            model_path = os.path.join(os.path.dirname(__file__), "..", "..", "model")
            if os.path.exists(model_path):
                self.model = Model(model_path)
                self.recognizer = KaldiRecognizer(self.model, 16000)
                logger.info("Vosk offline wake-word model loaded.")
                return True
            else:
                logger.warning(f"Vosk model not found at {model_path}. Wake-word disabled.")
                return False
        except ImportError:
            logger.warning("Vosk not installed. Wake-word disabled.")
            return False

    def _audio_callback(self, indata, frames, time, status):
        """This is called by sounddevice for each audio block."""
        if status:
            logger.debug(f"Audio status: {status}")
        self._q.put(bytes(indata))

    def _daemon_loop(self):
        if not self._init_vosk():
            return

        logger.info("Wake-word daemon listening for 'hey optimus'...")
        try:
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                                   channels=1, callback=self._audio_callback):
                while self._running:
                    data = self._q.get()
                    if data is None:
                        break
                    if self.recognizer.AcceptWaveform(data):
                        res = json.loads(self.recognizer.Result())
                        text = res.get("text", "")
                        if "hey" in text and "optimus" in text:
                            logger.info("WAKE WORD DETECTED: 'Hey Optimus'")
                            # Push to asyncio loop thread-safely
                            if hasattr(self, '_loop') and self._loop:
                                try:
                                    self._loop.call_soon_threadsafe(
                                        lambda: get_wake_queue().put_nowait(True)
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to push wake event: {e}")
        except Exception as e:
            logger.error(f"Wake-word daemon crashed: {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        try:
            self._loop = asyncio.get_running_loop()
            global WAKE_EVENT_QUEUE
            if WAKE_EVENT_QUEUE is None:
                WAKE_EVENT_QUEUE = asyncio.Queue()
        except RuntimeError:
            self._loop = None
        self._thread = threading.Thread(target=self._daemon_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._q.put(None)
        if self._thread:
            self._thread.join(timeout=2)

wake_word_engine = WakeWordDaemon()
