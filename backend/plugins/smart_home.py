"""
smart_home.py — Home Assistant REST/WebSocket API Integration v5.1
==================================================================
Eliminates simulated webhooks. Interfaces directly with Home Assistant
via secure environmental configuration variables ('HASS_URL', 'HASS_LONG_LIVED_ACCESS_TOKEN').
"""

import os
import aiohttp
from typing import Any

PLUGIN_METADATA: dict[str, Any] = {
    "name": "smart_home",
    "description": "Native Home Assistant integration to turn on/off devices, adjust climate entities, and read active home states.",
    "keywords": ["smart home", "lights", "turn on", "turn off", "device", "home assistant", "hass", "thermostat"],
}

_hass_session: aiohttp.ClientSession | None = None

async def _get_hass_session() -> aiohttp.ClientSession:
    global _hass_session
    if _hass_session is None or _hass_session.closed:
        _hass_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=10, limit_per_host=5),
            timeout=aiohttp.ClientTimeout(total=10)
        )
    return _hass_session

async def execute(args: dict = None) -> str:
    if not args or "action" not in args or "entity_id" not in args:
        return "Error: Both 'action' (e.g., turn_on, turn_off) and 'entity_id' (e.g., light.living_room) must be provided."

    action = args["action"].lower().replace(" ", "_")
    entity_id = args["entity_id"].lower()

    hass_url = os.getenv("HASS_URL")
    hass_token = os.getenv("HASS_LONG_LIVED_ACCESS_TOKEN")

    if not hass_url or not hass_token:
        # Fallback to simulation ONLY if credentials are not configured,
        # but explicitly log that it is a fallback due to missing config.
        return f"[Home Assistant] Simulation Fallback: Sent '{action}' to '{entity_id}'. (HASS_URL or HASS_LONG_LIVED_ACCESS_TOKEN not set in environment)."

    headers = {
        "Authorization": f"Bearer {hass_token}",
        "Content-Type": "application/json",
    }
    
    # Map actions to HASS domain services (e.g., light.turn_on)
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
    
    if action in ["on", "turn_on"]:
        service = "turn_on"
    elif action in ["off", "turn_off"]:
        service = "turn_off"
    elif action == "toggle":
        service = "toggle"
    else:
        # Pass raw action if it's something specific like 'set_temperature'
        service = action

    api_endpoint = f"{hass_url.rstrip('/')}/api/services/{domain}/{service}"
    payload = {"entity_id": entity_id}
    
    # Merge any extra parameters (like brightness, temperature)
    for k, v in args.items():
        if k not in ["action", "entity_id", "command", "query", "approved"]:
            payload[k] = v

    try:
        session = await _get_hass_session()
        async with session.post(api_endpoint, headers=headers, json=payload, timeout=10.0) as response:
            response.raise_for_status()
            data = await response.json()
            return f"[Home Assistant] Successfully executed '{service}' on '{entity_id}'. State changes: {data}"
    except Exception as e:
        return f"[Home Assistant] Connection error: {e}"
