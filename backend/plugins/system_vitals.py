"""
system_vitals.py — Async-native system telemetry plugin.
Uses asyncio.to_thread to prevent event-loop blocking on psutil blocking calls.
"""
from __future__ import annotations

import asyncio
import platform
import time
from typing import Any

import psutil

PLUGIN_METADATA: dict[str, Any] = {
    "name": "system_vitals",
    "description": (
        "Returns real-time CPU, RAM, disk, network I/O, and uptime metrics "
        "for the local machine without blocking the async event loop."
    ),
    "keywords": [
        "cpu", "ram", "memory", "usage", "vitals", "system",
        "disk", "network", "uptime", "stats", "performance",
    ],
}

# ---------------------------------------------------------------------------
# Internal blocking collector — run inside asyncio.to_thread
# ---------------------------------------------------------------------------
def _collect_vitals() -> dict[str, Any]:
    cpu_pct   = psutil.cpu_percent(interval=0.3)
    cpu_freq  = psutil.cpu_freq()
    cpu_count = psutil.cpu_count(logical=True)

    vm        = psutil.virtual_memory()
    swap      = psutil.swap_memory()

    disk      = psutil.disk_usage("/")
    net_io    = psutil.net_io_counters()

    boot_ts   = psutil.boot_time()
    uptime_s  = int(time.time() - boot_ts)
    h, rem    = divmod(uptime_s, 3600)
    m, s      = divmod(rem, 60)

    return {
        "cpu_pct":        cpu_pct,
        "cpu_freq_mhz":   round(cpu_freq.current, 1) if cpu_freq else 0.0,
        "cpu_cores":      cpu_count,
        "ram_pct":        vm.percent,
        "ram_used_gb":    round(vm.used  / 1024**3, 2),
        "ram_total_gb":   round(vm.total / 1024**3, 2),
        "swap_pct":       swap.percent,
        "disk_pct":       disk.percent,
        "disk_used_gb":   round(disk.used  / 1024**3, 1),
        "disk_total_gb":  round(disk.total / 1024**3, 1),
        "net_sent_mb":    round(net_io.bytes_sent / 1024**2, 2),
        "net_recv_mb":    round(net_io.bytes_recv / 1024**2, 2),
        "uptime":         f"{h}h {m}m {s}s",
        "platform":       platform.platform(),
    }


# ---------------------------------------------------------------------------
# Async execute entrypoint
# ---------------------------------------------------------------------------
async def execute(args: dict | None = None) -> str:  # type: ignore[override]
    v = await asyncio.to_thread(_collect_vitals)
    return (
        f"CPU:      {v['cpu_pct']}% @ {v['cpu_freq_mhz']} MHz  ({v['cpu_cores']} cores)\n"
        f"RAM:      {v['ram_pct']}%  ({v['ram_used_gb']} GB / {v['ram_total_gb']} GB)\n"
        f"Swap:     {v['swap_pct']}%\n"
        f"Disk:     {v['disk_pct']}%  ({v['disk_used_gb']} GB / {v['disk_total_gb']} GB used)\n"
        f"Network:  ↑ {v['net_sent_mb']} MB sent  |  ↓ {v['net_recv_mb']} MB recv\n"
        f"Uptime:   {v['uptime']}\n"
        f"Platform: {v['platform']}"
    )


# ---------------------------------------------------------------------------
# Synchronous shim — plugin_manager calls execute() synchronously;
# transparently bridges into async context when no loop is running.
# ---------------------------------------------------------------------------
def _sync_execute(args: dict | None = None) -> str:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, execute(args)).result()
        return loop.run_until_complete(execute(args))
    except Exception as exc:
        return f"Error collecting vitals: {exc}"


# Plugin manager expects a synchronous callable named `execute`
execute = _sync_execute  # type: ignore[assignment]
