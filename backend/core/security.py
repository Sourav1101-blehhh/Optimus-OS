import os
import hmac
import asyncio
import logging

logger = logging.getLogger("optimus.security")

# Global Hardware Mutex Lock
# Used to serialize access to the display/cursor across concurrent multi-agent executions.
hardware_lock = asyncio.Lock()

def validate_boot_token(token: str) -> bool:
    """
    Validates the incoming token against the secure OPTIMUS_BOOT_TOKEN generated at startup.
    Uses hmac.compare_digest for constant-time cryptographic comparison to prevent timing attacks.
    """
    boot_token = os.environ.get("OPTIMUS_BOOT_TOKEN")
    if not boot_token:
        # If no token was generated (e.g. running uvicorn directly during dev without wrapper),
        # we reject all connections to enforce secure defaults.
        logger.error("Security Fault: OPTIMUS_BOOT_TOKEN not set in environment.")
        return False
        
    if not token:
        logger.warning("Security Warning: Missing boot token in request.")
        return False

    return hmac.compare_digest(boot_token, token)
