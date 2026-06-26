"""
plugin_manager.py — Optimus OS Plugin Manager v5.0
====================================================
Concurrency Architecture:
    A shared asyncio.Semaphore(16) limits simultaneous plugin executions to
    prevent thread pool exhaustion when many requests arrive in parallel.

    Plugin dispatch uses inspect.iscoroutinefunction() to route execution:
      - Native async plugins: awaited directly in the event loop (zero thread overhead)
      - Synchronous plugins:  offloaded via asyncio.to_thread() — no nested event loops,
        no auxiliary asyncio.run() calls, no ThreadPoolExecutor wrapping.

Validation:
    Every plugin invocation is pre-validated through the PluginInput Pydantic v2 model.
    Unrecognised keys are accepted via `model_config = ConfigDict(extra='allow')` so
    plugin-specific args (e.g. 'path', 'url') pass through cleanly.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
import pkgutil
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, ValidationError
from pydantic import ConfigDict

logger = logging.getLogger("OptimusPluginManager")


from pydantic import BaseModel, ValidationError, Field

# ---------------------------------------------------------------------------
# Plugin Input Contract — Pydantic v2
# ---------------------------------------------------------------------------
class PluginInput(BaseModel):
    """
    Shared validation model for all plugin invocations.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    command: str = Field(max_length=500000)
    query: str = Field(default="", max_length=100000)
    approved: bool = Field(default=False)


# ---------------------------------------------------------------------------
# Plugin Manager
# ---------------------------------------------------------------------------
class PluginManager:
    """
    Discovers, loads, validates, and executes Optimus plugins.

    Concurrency contract:
        _semaphore: asyncio.Semaphore(16) — at most 16 plugin calls may run
        concurrently across all WebSocket sessions.  This prevents the default
        ThreadPoolExecutor from being starved when many synchronous plugins are
        dispatched in parallel.  The limit is deliberately set to 16 (half the
        typical pool ceiling of 32) to leave headroom for telemetry and other
        background tasks.
    """

    def __init__(self, plugin_dir: str) -> None:
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Dict[str, Any]] = {}
        self._semaphore_inst: Optional[asyncio.Semaphore] = None

    @property
    def _semaphore(self) -> asyncio.Semaphore:
        if self._semaphore_inst is None:
            self._semaphore_inst = asyncio.Semaphore(int(os.getenv("OPTIMUS_PLUGIN_CONCURRENCY", "16")))
        return self._semaphore_inst

    # ------------------------------------------------------------------
    # Discovery & Loading
    # ------------------------------------------------------------------
    def load_plugins(self) -> None:
        """
        Scans the `backend/plugins/` directory for modules that expose both
        `PLUGIN_METADATA` (dict) and `execute` (callable).

        Called once during application startup via asyncio.to_thread so it
        does not block the event loop.
        """
        self.plugins.clear()
        plugin_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "plugins")
        )
        if not os.path.exists(plugin_path):
            os.makedirs(plugin_path)

        for _, module_name, _ in pkgutil.iter_modules([plugin_path]):
            try:
                module = importlib.import_module(f"backend.plugins.{module_name}")
                if hasattr(module, "PLUGIN_METADATA") and hasattr(module, "execute"):
                    name = module.PLUGIN_METADATA["name"]
                    
                    # Dynamically extract expected arguments from the execute function
                    try:
                        import re, inspect
                        src = inspect.getsource(module.execute)
                        args = set(re.findall(r'args(?:\[\"|\.get\(\")([a-zA-Z0-9_]+)\"', src))
                        if args:
                            module.PLUGIN_METADATA["description"] += f" REQUIRED JSON ARGS: {list(args)}"
                    except Exception:
                        pass
                        
                    self.plugins[name] = {
                        "metadata": module.PLUGIN_METADATA,
                        "execute":  module.execute,
                        "is_async": inspect.iscoroutinefunction(module.execute),
                    }
                    kind = "async" if self.plugins[name]["is_async"] else "sync"
                    logger.info(f"Loaded plugin [{kind}]: {name}")
            except Exception as exc:
                logger.error(f"Failed to load plugin '{module_name}': {exc}")

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------
    def get_plugin(self, name: str) -> Optional[Callable]:
        """Returns the execute callable for the named plugin, or None."""
        entry = self.plugins.get(name)
        return entry["execute"] if entry else None

    def get_all_metadata(self) -> list[dict]:
        """Returns a list of metadata dicts for all loaded plugins."""
        return [p["metadata"] for p in self.plugins.values()]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate_plugin_args(self, args: dict) -> dict:
        """
        Validates and normalises plugin args through the PluginInput model.
        Raises ValueError with a descriptive message on validation failure.
        Extra keys are preserved via `extra='allow'`.
        """
        try:
            validated = PluginInput(**args)
            validated_fields = validated.model_dump(by_alias=True, exclude_unset=True)
            # Merge: start with original args, then overlay only the fields that were explicitly validated
            return {**args, **validated_fields}
        except ValidationError as exc:
            raise ValueError(f"Plugin argument validation failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Async execution with concurrency guard
    # ------------------------------------------------------------------
    async def execute_async(self, plugin_name: str, args: dict) -> str:
        """
        Execute a plugin by name with full concurrency control and routing.

        Flow:
            1. Validate args via Pydantic.
            2. Acquire the shared semaphore slot (blocks if 16 are already in use).
            3. If the plugin's `execute` is a native coroutine function, await it
               directly in the event loop — no thread overhead.
            4. If the plugin is synchronous, run it in the default thread pool via
               asyncio.to_thread() — no nested asyncio.run(), no auxiliary
               ThreadPoolExecutor spawning.
            5. Release the semaphore slot on completion (or exception).

        The semaphore is acquired AFTER validation so that malformed frames
        never consume a concurrency slot.
        """
        try:
            valid_args = self.validate_plugin_args(args)
        except ValueError as exc:
            return f"Error: {exc}"

        func = self.get_plugin(plugin_name)
        if func is None:
            return f"Error: Plugin '{plugin_name}' not found in registry."

        is_async: bool = self.plugins[plugin_name]["is_async"]

        async with self._semaphore:
            try:
                if is_async:
                    # Native coroutine — await directly; zero thread overhead
                    return await func(valid_args)
                else:
                    # Synchronous plugin — offload to thread pool without
                    # creating a nested event loop.  asyncio.to_thread uses
                    # the running loop's default executor, which is a bounded
                    # ThreadPoolExecutor managed by the event loop.
                    return await asyncio.to_thread(func, valid_args)
            except Exception as exc:
                logger.error(f"Plugin '{plugin_name}' raised during execution: {exc}")
                return f"Error executing plugin '{plugin_name}': {exc}"


# ---------------------------------------------------------------------------
# Module-level singleton — shared across all WebSocket sessions
# (agent instances are per-connection; the plugin registry is global and
# read-only after load_plugins() completes)
# ---------------------------------------------------------------------------
plugin_manager = PluginManager(plugin_dir="backend.plugins")
