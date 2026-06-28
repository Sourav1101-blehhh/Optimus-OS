import json
import os
import asyncio

PLUGIN_METADATA = {
    "name": "memory",
    "description": "Reads and writes notes, reminders, or general memories to a local JSON database.",
    "keywords": ["remember", "note", "memory", "remind", "forget", "list", "save"]
}

DB_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "memory.json")
memory_lock = asyncio.Lock()

async def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        def _read():
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        return await asyncio.to_thread(_read)
    except Exception:
        return {}

async def save_db(data):
    def _write():
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    await asyncio.to_thread(_write)

async def execute(args: dict = None) -> str:
    if not args or "action" not in args:
        return "Error: Please provide an 'action' ('read' or 'write')."
        
    action = args["action"].lower()
    
    if action == "write":
        async with memory_lock:
            db = await load_db()
            key = args.get("key", "General Notes")
            value = args.get("value")
            if not value:
                return "Error: No value to remember."
            
            if key not in db:
                db[key] = []
            db[key].append(value)
            if len(db[key]) > 100:
                db[key] = db[key][-100:]
            
            await save_db(db)
            return f"Successfully saved to memory under '{key}'."
            
    elif action == "read":
        async with memory_lock:
            db = await load_db()
        key = args.get("key")
        if not db:
            return "Memory is currently empty."
            
        if key:
            if key in db:
                items = "\n".join([f"- {item}" for item in db[key]])
                return f"Memories for '{key}':\n{items}"
            else:
                return f"No memories found for '{key}'."
        else:
            # Read all
            output = []
            for k, v in db.items():
                items = "\n".join([f"  - {item}" for item in v])
                output.append(f"{k}:\n{items}")
            return "All Memories:\n" + "\n".join(output)
            
    elif action == "clear":
        async with memory_lock:
            db = await load_db()
            key = args.get("key")
            if key and key in db:
                del db[key]
                await save_db(db)
                return f"Cleared memories for '{key}'."
            else:
                return "Error: Provide a valid 'key' to clear."
            
    return f"Unknown action: {action}"
