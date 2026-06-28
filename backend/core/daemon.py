import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.core.agent import OptimusAgent
from backend.main import manager

logger = logging.getLogger("ProactiveDaemon")
scheduler = AsyncIOScheduler()

async def proactive_email_check():
    if not manager.active_connections:
        return # Skip if no active UI
        
    logger.info("Running proactive email check...")
    try:
        agent = OptimusAgent()
        # Internal query so it doesn't pollute user history
        prompt = (
            "Read my recent unread emails. If there are any urgent or highly important emails, "
            "summarize them briefly. If there are NO urgent emails, output EXACTLY the phrase 'NO_ACTION_NEEDED'."
        )
        
        full_response = ""
        async for token in agent.process_message_stream(prompt, internal=True, max_depth=3):
            full_response += token
            
        full_response = full_response.strip()
        
        if "NO_ACTION_NEEDED" not in full_response and full_response:
            logger.info("Proactive email check found urgent messages. Pushing to UI.")
            # Prefix with a clear indicator
            alert = f"🔔 **Proactive Alert (Email):**\n\n{full_response}"
            await manager.broadcast({"type": "chat", "data": alert})
            
            # Optionally trigger speech
            # await manager.broadcast({"type": "speech_play", "data": "You have urgent emails."})
            
    except Exception as e:
        logger.error(f"Proactive email check failed: {e}")

def start_daemons():
    # Run email check every 15 minutes
    scheduler.add_job(proactive_email_check, 'interval', minutes=15)
    scheduler.start()
    logger.info("Proactive APScheduler daemons armed (Intervals: 15m).")
