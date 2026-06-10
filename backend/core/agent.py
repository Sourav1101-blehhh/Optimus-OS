"""
agent.py — Optimus OS Agent Orchestrator v5.0
==============================================
Key architectural upgrades from v4:

1. NATIVE ASYNC GEMINI STREAMING
   Uses `client.aio.models.generate_content_stream()` (the official Google GenAI
   async streaming interface).  The v4 `run_in_executor` synchronous wrapper has
   been completely removed.  Tokens are yielded as they arrive from the API,
   providing true real-time streaming with bounded `max_output_tokens=2048`.

2. DUAL-TIER SEMANTIC CACHE (per-instance, not class-level)
   Each OptimusAgent instance carries its own isolated cache so that sessions
   cannot serve cached responses from other users.
     Tier 0 — Exact SHA-256 bitmask:  O(1) lookup, perfect-match only.
     Tier 1 — Tri-gram Jaccard similarity:  85% threshold fuzzy match using
              the top-12 most-frequent trigrams.  Only Tier-0 misses fall
              through to Tier 1.
   Both tiers share a single 512-entry LRU OrderedDict.

3. ELEVATED TOOL RECURSION (max_depth = 5)
   The autonomous agentic tool-use loop now supports up to 5 recursive
   tool invocations.  Depth violations no longer silently truncate; they
   emit a structured {"type": "tool_depth_exceeded"} JSON payload that the
   frontend can surface as a visible warning.

4. SYNCHRONOUS SHIM REMOVAL
   The legacy `execute()` synchronous shim in terminal.py was the only caller
   of `asyncio.run()` inside a thread.  `execute_plugin_async()` in this module
   now exclusively routes through `plugin_manager.execute_async()`, which
   handles async/sync detection internally — no auxiliary event loops created.

5. RING-BUFFER CONVERSATION HISTORY (per-instance)
   The v4 class-level `_store`, `_fp_index`, `_history_matrix` etc. have been
   moved to instance-level `__init__` attributes so each connection's history
   is fully isolated.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import unicodedata
from collections import OrderedDict
from typing import AsyncIterator, Optional

import httpx
from anthropic import AsyncAnthropic
import chromadb
from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from backend.core.plugin_manager import plugin_manager

load_dotenv()
logger = logging.getLogger("OptimusAgent")


# ---------------------------------------------------------------------------
# Desktop operation helper (used by Gemini function-calling)
# ---------------------------------------------------------------------------
def execute_desktop_operation(app_name: str, operations_json: str) -> str:
    """
    Thin shim that routes Gemini function-call payloads to the desktop
    automation plugin.  Accepts a JSON string of operation descriptors.
    """
    try:
        ops = (
            json.loads(operations_json)
            if isinstance(operations_json, str)
            else operations_json
        )
    except Exception:
        ops = [{"action": "type", "text": str(operations_json)}]
    from backend.plugins.desktop_automation import execute as _da_execute
    return _da_execute({"app_name": app_name, "operations": ops})


# ---------------------------------------------------------------------------
# OptimusAgent — fully isolated per WebSocket connection
# ---------------------------------------------------------------------------
class OptimusAgent:
    """
    Orchestrates multi-engine LLM communication, conversation memory,
    dual-tier semantic caching, and plugin tool-use for a SINGLE WebSocket
    session.

    Instantiated once per connection in ConnectionManager.connect() so that
    conversation history, cache entries, and LLM client handles are never
    shared between concurrent users.
    """

    # ------------------------------------------------------------------
    # Cache constants
    # ------------------------------------------------------------------
    _CACHE_MAX:   int = 512   # Hard LRU eviction cap
    _NGRAM_N:     int = 3     # Trigram size for Tier-1 fingerprinting
    _NGRAM_TOP:   int = 12    # Top-N trigrams used per fingerprint
    _JACCARD_MIN: float = 0.85  # Minimum Jaccard similarity for Tier-1 hit

    # Recursive tool-use depth limit
    _MAX_TOOL_DEPTH: int = 5

    def __init__(self) -> None:
        self.name = "Optimus"

        # ── LLM Client Initialisation ─────────────────────────────────────
        self.gemini_client: Optional[genai.Client] = None
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if gemini_key and gemini_key != "YOUR_API_KEY_HERE":
            try:
                self.gemini_client = genai.Client(api_key=gemini_key)
                logger.info("Gemini client initialised (async streaming enabled).")
            except Exception as exc:
                logger.error(f"Gemini init error: {exc}")

        self.gpt_client: Optional[AsyncOpenAI] = None
        gpt_key = os.getenv("OPENAI_API_KEY", "")
        if gpt_key:
            try:
                self.gpt_client = AsyncOpenAI(api_key=gpt_key)
                logger.info("OpenAI async client initialised.")
            except Exception as exc:
                logger.error(f"OpenAI init error: {exc}")

        self.deepseek_client: Optional[AsyncOpenAI] = None
        ds_key  = os.getenv("DEEPSEEK_API_KEY", "")
        ds_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        if ds_key:
            try:
                self.deepseek_client = AsyncOpenAI(api_key=ds_key, base_url=ds_base)
                logger.info(f"DeepSeek async client initialised (base: {ds_base}).")
            except Exception as exc:
                logger.error(f"DeepSeek init error: {exc}")

        self.anthropic_client: Optional[AsyncAnthropic] = None
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            try:
                self.anthropic_client = AsyncAnthropic(api_key=anthropic_key)
                logger.info("Anthropic async client initialised.")
            except Exception as exc:
                logger.error(f"Anthropic init error: {exc}")

        # Persistent httpx client for Ollama (keep-alive connection pool)
        self._ollama_http: httpx.AsyncClient = httpx.AsyncClient(
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=50),
            timeout=30.0,
            headers={"Connection": "keep-alive"},
        )

        # ── Per-Instance Conversation History ──────
        # We no longer hard-cap to 20 frames blindly. We will allow it to grow
        # and periodically compress the oldest 10 into a summary.
        self._history_matrix: list[dict] = []

        # ── Per-Instance Dual-Tier Cache ──────────────────────────────────
        # Single OrderedDict used as an LRU store for both tiers.
        # Key: SHA-256 hex string.  Value: cached response string.
        self._cache_store:   OrderedDict[str, str] = OrderedDict()
        # Tier-1 index: trigram fingerprint string -> canonical SHA-256 key
        self._fp_index:      dict[str, str] = {}

        # ── Persistent Episodic Memory (ChromaDB) ─────────────────────────
        try:
            db_path = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")
            self._chroma_client = chromadb.PersistentClient(path=db_path)
            self._memory_col = self._chroma_client.get_or_create_collection(
                name="optimus_episodic_memory",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("ChromaDB PersistentClient connected to optimus_episodic_memory.")
        except Exception as exc:
            logger.error(f"ChromaDB initialization failed: {exc}")
            self._chroma_client = None
            self._memory_col = None

        # Persistent summary built by the background pruner
        self.session_summary: str = ""

        logger.debug("OptimusAgent instance created (isolated session).")

    # ------------------------------------------------------------------
    # Conversation History & Dynamic Context Pruning
    # ------------------------------------------------------------------
    def _append_history(
        self, role: str, content: str, image_data: Optional[str] = None
    ) -> None:
        entry: dict = {"role": role, "content": content}
        if image_data:
            entry["image_data"] = image_data
            
        self._history_matrix.append(entry)
        
        # Trigger background pruner when context window gets too large
        if len(self._history_matrix) > 20:
            asyncio.create_task(self._prune_history_background())

    async def _prune_history_background(self) -> None:
        """
        Compresses the oldest 10 turns into a clean markdown "Current Session State Summary",
        appends it directly to the system instructions header, wipes those 10 raw frames 
        from active memory, and ensures they are committed to ChromaDB.
        """
        if len(self._history_matrix) <= 20:
            return
            
        logger.info("Context window hit 20 frames. Triggering background memory pruner.")
        
        # Extract oldest 10 frames
        oldest_frames = self._history_matrix[:10]
        
        # Build prompt for micro-LLM summarization task
        transcript = "\n".join([f"{msg['role'].upper()}: {msg['content'][:200]}..." for msg in oldest_frames])
        prompt = f"Summarize the following conversation history into a concise, factual markdown block detailing the current session state, established context, and any ongoing tasks or goals. Keep it under 150 words.\n\n{transcript}"
        
        # We use Ollama as the micro-LLM for privacy and speed
        summary = "[SESSION SUMMARY UNAVAILABLE]"
        try:
            async with self._ollama_http.stream(
                "POST", "http://127.0.0.1:11434/api/generate",
                json={"model": "deepseek-coder-v2", "prompt": prompt, "stream": False},
                timeout=15.0
            ) as response:
                if response.status_code == 200:
                    raw_bytes = await response.aread()
                    summary_resp = json.loads(raw_bytes.decode('utf-8'))
                    summary = summary_resp.get("response", "").strip()
        except Exception as e:
            logger.warning(f"Failed to generate background summary: {e}")
            
        # Update system instructions with the new summary (conceptually, we store it to prepend)
        self.session_summary = summary
        
        # CONTINUOUS LEARNING: Commit to ChromaDB Episodic Memory
        if self._memory_col:
            try:
                import uuid
                doc_id = str(uuid.uuid4())
                # Add to vector database asynchronously
                await asyncio.to_thread(
                    self._memory_col.add,
                    documents=[summary],
                    metadatas=[{"type": "background_prune_summary"}],
                    ids=[doc_id]
                )
                logger.info(f"Committed session summary to episodic memory (ID: {doc_id}).")
            except Exception as e:
                logger.warning(f"Failed to commit to episodic memory: {e}")
        
        # Wipe the oldest 10 frames from active memory list
        self._history_matrix = self._history_matrix[10:]
        logger.info("Background memory prune complete. Active frames reduced by 10.")

    def _get_history(self) -> list[dict]:
        return self._history_matrix

    def purge_base64_assets(self) -> None:
        """
        Strips image_data fields from all history entries after inference
        completes.  Prevents base64 image strings from being re-serialised
        into every subsequent LLM request, which would inflate token counts
        and API costs on each follow-up message.
        """
        for entry in self._history_matrix:
            if entry and "image_data" in entry:
                del entry["image_data"]
        logger.debug("Context asset purge complete (base64 fields stripped).")

    @property
    def chat_history(self) -> list[dict]:
        """Returns history entries in chronological order."""
        return [e for e in self._history_matrix if e]

    # ------------------------------------------------------------------
    # Dual-Tier Semantic Cache
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise(text: str) -> str:
        """NFKC-normalise, lowercase, strip punctuation, collapse whitespace."""
        t = unicodedata.normalize("NFKC", text).lower()
        t = re.sub(r"[^\w\s]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    @classmethod
    def _sha256_key(cls, prompt: str) -> str:
        """Tier-0: SHA-256 hex digest of the raw prompt string."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def _trigram_fingerprint(self, prompt: str) -> str:
        """
        Tier-1: Builds a canonical fingerprint string from the top-N most
        frequent trigrams of the normalised prompt.  Used as a lookup key
        in self._fp_index.
        """
        norm = self._normalise(prompt)
        ngrams: dict[str, int] = {}
        for i in range(len(norm) - self._NGRAM_N + 1):
            g = norm[i : i + self._NGRAM_N]
            ngrams[g] = ngrams.get(g, 0) + 1
        top = sorted(ngrams, key=lambda g: (-ngrams[g], g))[: self._NGRAM_TOP]
        return "|".join(top)

    def _jaccard_similarity(self, fp_a: str, fp_b: str) -> float:
        """
        Computes the Jaccard similarity between two fingerprint strings
        (treating each |-delimited token as a set element).
        Returns a float in [0.0, 1.0].
        """
        set_a = set(fp_a.split("|"))
        set_b = set(fp_b.split("|"))
        if not set_a and not set_b:
            return 1.0
        intersection = len(set_a & set_b)
        union        = len(set_a | set_b)
        return intersection / union if union else 0.0

    def _cache_lookup(self, prompt: str) -> Optional[str]:
        """
        Two-tier cache lookup:

        Tier 0 — Exact match (O(1)):
            SHA-256 hash of the raw prompt is checked against the LRU store.
            On hit: move entry to MRU position and return value.

        Tier 1 — Fuzzy match (Jaccard ≥ 85%):
            Compute the trigram fingerprint of the prompt.
            Iterate over _fp_index entries, computing Jaccard similarity.
            If the best candidate exceeds _JACCARD_MIN and its canonical key
            still exists in _cache_store, return that cached value.
            This handles minor paraphrasings of identical queries.
        """
        # Tier 0 — exact hash
        t0_key = self._sha256_key(prompt)
        if t0_key in self._cache_store:
            self._cache_store.move_to_end(t0_key)
            logger.debug("Cache Tier-0 HIT (exact SHA-256).")
            return self._cache_store[t0_key]

        # Tier 1 — fuzzy tri-gram Jaccard similarity
        query_fp = self._trigram_fingerprint(prompt)
        best_sim: float = 0.0
        best_key: Optional[str] = None

        for stored_fp, canonical_key in self._fp_index.items():
            if canonical_key not in self._cache_store:
                continue
            sim = self._jaccard_similarity(query_fp, stored_fp)
            if sim > best_sim:
                best_sim, best_key = sim, canonical_key

        if best_sim >= self._JACCARD_MIN and best_key:
            self._cache_store.move_to_end(best_key)
            logger.debug(f"Cache Tier-1 HIT (Jaccard={best_sim:.2f} >= {self._JACCARD_MIN}).")
            return self._cache_store[best_key]

        return None

    def _cache_write(self, prompt: str, response: str) -> None:
        """
        Write a prompt→response pair into the LRU cache.

        Eviction: if the store has reached _CACHE_MAX entries, the least-
        recently-used entry (first item of the OrderedDict) is popped and
        its associated Tier-1 fingerprint index entries are cleaned up.
        """
        t0_key = self._sha256_key(prompt)
        fp_key = self._trigram_fingerprint(prompt)

        # Evict LRU entries until below cap
        while len(self._cache_store) >= self._CACHE_MAX:
            evicted_key, _ = self._cache_store.popitem(last=False)
            dead_fps = [f for f, k in self._fp_index.items() if k == evicted_key]
            for f in dead_fps:
                del self._fp_index[f]

        self._cache_store[t0_key] = response
        self._cache_store.move_to_end(t0_key)
        self._fp_index[fp_key] = t0_key

    # ------------------------------------------------------------------
    # System Prompt Builder
    # ------------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        plugins_info = [
            f"- {name}: {p['metadata'].get('description')}. Keywords: {p['metadata'].get('keywords')}"
            for name, p in plugin_manager.plugins.items()
        ]
        tools_list = "\n".join(plugins_info)
        return f"""You are Optimus, an advanced autonomous local AI assistant (like Jarvis).
Your goal is to help the user by having conversations and executing actions on their machine.

You have access to the following tools:
{tools_list}

If you need to use a tool to fulfill the user's request, you MUST output ONLY a valid JSON block in this exact format:
```json
{{
    "tool": "<tool_name>",
    "args": {{
        "<arg_name>": "<arg_value>"
    }}
}}
```
If you do not need to use a tool, just respond with normal text. Keep responses concise and conversational.
"""

    # ------------------------------------------------------------------
    # Plugin Execution
    # ------------------------------------------------------------------
    async def execute_plugin_async(self, plugin_name: str, args: dict) -> str:
        """
        Delegates plugin execution entirely to the plugin_manager's async
        execution path, which handles semaphore acquisition, validation,
        and async/sync routing internally.

        No nested event loops or auxiliary ThreadPoolExecutors are created
        here — all concurrency control lives in plugin_manager.execute_async().
        """
        return await plugin_manager.execute_async(plugin_name, args)

    # ------------------------------------------------------------------
    # LLM Engine Streams
    # ------------------------------------------------------------------
    async def _gemini_stream(
        self,
        system_prompt: str,
        history: list[dict],
        image_data: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Native async Gemini streaming using `client.aio.models.generate_content_stream`.

        CRITICAL UPGRADE from v4:
            v4 used `run_in_executor(None, lambda: client.models.generate_content(...))`
            which:
              (a) consumed a thread pool slot for the entire request duration
              (b) returned the full response as a single blob (no true streaming)
              (c) added ~10–30 ms thread handoff latency

            v5 calls `client.aio.models.generate_content_stream()` — the official
            async streaming method in the Google GenAI SDK.  Tokens are yielded
            as they arrive from the API with zero thread overhead and bounded
            `max_output_tokens=2048` to cap credit consumption.

        Function-calling (desktop automation) is detected in the final resolved
        response and dispatched immediately.
        """
        if not self.gemini_client:
            yield "Error: GEMINI_API_KEY missing or invalid."
            return
        try:
            contents: list = []
            for msg in history:
                role = msg["role"]
                parts: list = [types.Part.from_text(text=msg["content"])]
                if msg.get("image_data"):
                    try:
                        raw = msg["image_data"]
                        img_b64 = raw.split(",")[-1]
                        mime = (
                            raw.split(";")[0].split(":")[1]
                            if "data:" in raw
                            else "image/jpeg"
                        )
                        parts.append(
                            types.Part.from_bytes(
                                data=base64.b64decode(img_b64), mime_type=mime
                            )
                        )
                    except Exception as exc:
                        logger.error(f"Gemini image encode error: {exc}")
                contents.append(types.Content(role=role, parts=parts))

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=[execute_desktop_operation],
                temperature=0.65,       # Lower temperature = more deterministic, credit-efficient
                max_output_tokens=2048, # Hard cap to prevent runaway generation costs
            )

            # Native async streaming — no run_in_executor, no thread overhead
            response_stream = await self.gemini_client.aio.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=contents,
                config=config,
            )
            async for chunk in response_stream:
                # Handle function calls embedded in streaming chunks
                if hasattr(chunk, 'function_calls') and chunk.function_calls:
                    for call in chunk.function_calls:
                        if call.name == "execute_desktop_operation":
                            args = call.args
                            res = execute_desktop_operation(
                                args.get("app_name", ""),
                                args.get("operations_json") or args.get("operations", "[]"),
                            )
                            yield f"[Desktop Automation] {res}"
                    continue

                token = chunk.text if hasattr(chunk, 'text') else None
                if token:
                    yield token

        except Exception as exc:
            logger.error(f"Gemini stream error: {exc}")
            yield f"Gemini error: {exc}"

    async def _ollama_stream(
        self,
        system_prompt: str,
        history: list[dict],
        image_data: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Streams tokens from the local Ollama server.  Uses a persistent httpx
        keep-alive connection pool to avoid per-request TCP handshake overhead.

        Model selection:
            - If any history entry contains image_data → 'llava' (vision model)
            - Otherwise → 'deepseek-coder-v2' (text model)

        Fallback:  On any httpx connectivity or timeout error, transparently
        transitions to Gemini Flash without exposing the failure to the user.
        """
        url = "http://localhost:11434/api/chat"
        messages = [{"role": "system", "content": system_prompt}]
        has_images = False

        for msg in history:
            role = "assistant" if msg["role"] == "model" else "user"
            item: dict = {"role": role, "content": msg["content"]}
            if msg.get("image_data"):
                try:
                    item["images"] = [msg["image_data"].split(",")[-1]]
                    has_images = True
                except Exception:
                    pass
            messages.append(item)

        model_name = "llava" if has_images else "deepseek-coder-v2"
        payload = {
            "model":   model_name,
            "messages": messages,
            "stream":  True,
            "options": {
                "keep_alive": -1,
                "num_ctx":    4096,
                "num_predict": 1024,
            },
        }

        try:
            async with self._ollama_http.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

        except (httpx.ConnectError, httpx.TimeoutException, Exception) as exc:
            logger.warning(
                f"Ollama unavailable ({exc}), transitioning to Gemini Flash fallback."
            )
            async for token in self._gemini_stream(system_prompt, history, image_data):
                yield token

    async def _gpt_stream(
        self, system_prompt: str, history: list[dict]
    ) -> AsyncIterator[str]:
        """
        Streams tokens from GPT-4o via the AsyncOpenAI client.

        Reasoning effort is automatically elevated to 'high' when the last
        user message contains debugging keywords (traceback, exception, etc.)
        to maximise accuracy on error analysis tasks at the cost of slightly
        higher latency.
        """
        if not self.gpt_client:
            yield "Error: OPENAI_API_KEY missing. Set it in your .env file."
            return

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            role = "assistant" if msg["role"] == "model" else "user"
            content_list = []
            if msg.get("image_data"):
                content_list.append(
                    {"type": "image_url", "image_url": {"url": msg["image_data"]}}
                )
            content_list.append({"type": "text", "text": msg["content"]})
            messages.append({"role": role, "content": content_list})

        last_user = next(
            (m["content"] for m in reversed(history) if m["role"] == "user"), ""
        )
        reasoning_effort = (
            "high"
            if any(
                k in last_user.lower()
                for k in ["debug", "traceback", "exception", "error", "stack"]
            )
            else "medium"
        )

        try:
            stream = await self.gpt_client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=2048,
                stream=True,
                extra_body={"reasoning_effort": reasoning_effort},
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as exc:
            logger.error(f"GPT stream error: {exc}")
            yield f"GPT error: {exc}"

    async def _deepseek_stream(
        self, system_prompt: str, history: list[dict]
    ) -> AsyncIterator[str]:
        """Streams tokens from DeepSeek via the OpenAI-compatible async client."""
        if not self.deepseek_client:
            yield "Error: DEEPSEEK_API_KEY missing. Set it in your .env file."
            return
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            role = "assistant" if msg["role"] == "model" else "user"
            messages.append({"role": role, "content": msg["content"]})
        try:
            stream = await self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                max_tokens=2048,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as exc:
            logger.error(f"DeepSeek stream error: {exc}")
            yield f"DeepSeek error: {exc}"

    async def _anthropic_stream(
        self, system_prompt: str, history: list[dict]
    ) -> AsyncIterator[str]:
        """Streams tokens from Claude 3.5 Sonnet via the AsyncAnthropic client."""
        if not self.anthropic_client:
            yield "Error: ANTHROPIC_API_KEY missing. Set it in your .env file."
            return
        messages = [
            {
                "role": "assistant" if msg["role"] == "model" else "user",
                "content": msg["content"],
            }
            for msg in history
        ]
        try:
            async with self.anthropic_client.messages.stream(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            logger.error(f"Anthropic stream error: {exc}")
            yield f"Anthropic error: {exc}"

    # ------------------------------------------------------------------
    # Primary Orchestration Entry Point
    # ------------------------------------------------------------------
    async def process_message_stream(
        self,
        message:       str,
        image_data:    Optional[str] = None,
        engine:        str = "LOCAL",
        max_depth:     int = _MAX_TOOL_DEPTH,
        current_depth: int = 0,
    ) -> AsyncIterator[str]:
        """
        Primary async generator that orchestrates LLM inference and recursive
        plugin tool-use.

        Depth Guard:
            If current_depth exceeds max_depth (default: 5), yields a
            structured JSON warning payload that the frontend can surface
            as a visible UI notification rather than silently discarding it.

        Cache Check (depth 0 only):
            Before calling any LLM, the dual-tier cache is checked.  A hit
            yields the cached response immediately with zero API credits spent.

        Agentic Tool Loop:
            If the model's response contains a ```json ... ``` block with a
            'tool' key, the tool is executed and the result is injected into
            history.  The function then recurses (current_depth + 1) to allow
            the model to reason over the tool result.

        Context Asset Purge:
            In the `finally` block, purge_base64_assets() strips all image_data
            from history entries.  This runs even if an exception is raised,
            guaranteeing that base64 strings never accumulate across turns.
        """
        try:
            # ── Depth violation: structured warning, not silent truncation ───
            if current_depth > max_depth:
                warning = json.dumps({
                    "type":    "tool_depth_exceeded",
                    "message": (
                        f"Autonomous tool chain exceeded maximum depth of {max_depth}. "
                        "Halting to prevent runaway execution."
                    ),
                    "depth": current_depth,
                })
                yield warning
                return

            engine = engine.upper()

            if current_depth == 0:
                self._append_history("user", message, image_data)

            system_prompt = self._build_system_prompt()

            # ── Dual-tier cache check (depth 0 only) ─────────────────────────
            if current_depth == 0:
                cached = self._cache_lookup(message)
                if cached:
                    logger.info("Semantic cache HIT — zero-credit local yield.")
                    self._append_history("model", cached)
                    yield cached
                    return

            # ── Episodic Memory Retrieval (RAG) ──────────────────────────────
            if current_depth == 0 and self._memory_col:
                try:
                    results = await asyncio.to_thread(
                        self._memory_col.query,
                        query_texts=[message],
                        n_results=3
                    )
                    documents = results.get("documents", [[]])[0]
                    if documents:
                        memory_context = "\n---\n".join(documents)
                        system_prompt += f"\n\n[RECALLED CONTEXT - HISTORICAL INTERACTIONS]\n{memory_context}\n"
                        logger.info(f"RAG: Injected {len(documents)} episodic memories.")
                except Exception as exc:
                    logger.warning(f"RAG Retrieval failed: {exc}")

            # ── Engine selection ─────────────────────────────────────────────
            stream = None
            if engine in ("GPT", "OPENAI"):
                stream = self._gpt_stream(system_prompt, self.chat_history)
            elif engine == "DEEPSEEK":
                stream = self._deepseek_stream(system_prompt, self.chat_history)
            elif engine in ("ANTHROPIC", "CLAUDE"):
                stream = self._anthropic_stream(system_prompt, self.chat_history)
            elif engine == "GEMINI":
                # Catch Gemini HTTP initialization errors directly, fallback to Claude
                try:
                    stream = self._gemini_stream(system_prompt, self.chat_history, image_data)
                except Exception as e:
                    logger.error(f"Gemini init error: {e}. Failing over to Claude.")
                    stream = self._anthropic_stream(system_prompt, self.chat_history)
            else:
                # LOCAL = Ollama with Gemini fallback
                stream = self._ollama_stream(system_prompt, self.chat_history, image_data)

            # ── Stream tokens and accumulate full response ───────────────────
            response_parts: list[str] = []
            try:
                async for token in stream:
                    response_parts.append(token)
                    yield token
            except httpx.HTTPError as he:
                # Catch stream-time HTTP errors for Gemini and fallback to Claude
                if engine == "GEMINI":
                    logger.error(f"Gemini streaming HTTP Error: {he}. Failing over to Claude.")
                    yield "\n[Network Failover] Routing query to Anthropic Claude...\n"
                    stream = self._anthropic_stream(system_prompt, self.chat_history)
                    async for token in stream:
                        response_parts.append(token)
                        yield token
                else:
                    raise
            except Exception as e:
                # Pass up generic exceptions
                raise e

            full_response = "".join(response_parts)

            # ── Agentic tool-use detection ───────────────────────────────────
            if "```json" in full_response and '"tool":' in full_response:
                try:
                    json_str = (
                        full_response.split("```json")[1].split("```")[0].strip()
                    )
                    tool_call  = json.loads(json_str)
                    tool_name  = tool_call.get("tool")
                    tool_args  = tool_call.get("args", {})

                    self._append_history("model", full_response)
                    result = await self.execute_plugin_async(tool_name, tool_args)

                    if isinstance(result, str) and result.startswith("SCREENSHOT_BASE64:"):
                        img_b64  = result[len("SCREENSHOT_BASE64:"):]
                        img_url  = f"data:image/png;base64,{img_b64}"
                        follow_msg = "SYSTEM: Screenshot captured. Describe what you see."
                        self._append_history("user", follow_msg, img_url)
                    else:
                        follow_msg = f"SYSTEM: Tool '{tool_name}' returned:\n{result}"
                        self._append_history("user", follow_msg)

                    # Recurse with incremented depth counter
                    async for tok in self.process_message_stream(
                        "",
                        engine=engine,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                    ):
                        yield tok
                    return

                except Exception as exc:
                    logger.error(f"Tool call parse/exec error: {exc}")

            # ── Persist response and cache (depth 0 only) ────────────────────
            self._append_history("model", full_response)
            if (
                current_depth == 0
                and full_response
                and not full_response.startswith("Error:")
            ):
                self._cache_write(message, full_response)
                
                # Async Memory Commit to ChromaDB
                if self._memory_col:
                    try:
                        mem_id = hashlib.sha256(f"{message}{full_response}".encode('utf-8')).hexdigest()[:16]
                        doc_text = f"User: {message}\nOptimus: {full_response}"
                        
                        # Fire and forget async commit to thread pool
                        asyncio.create_task(
                            asyncio.to_thread(
                                self._memory_col.add,
                                documents=[doc_text],
                                ids=[mem_id]
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to commit memory to ChromaDB: {e}")

        finally:
            # Always purge base64 assets from history after inference completes
            # to prevent token count inflation on subsequent turns.
            self.purge_base64_assets()
