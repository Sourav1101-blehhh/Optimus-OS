import datetime
import json
import os

PLUGIN_METADATA = {
    "name": "scheduler",
    "description": "Manages a local schedule/calendar. Actions: 'add' (add an event with 'title', 'date', 'time'), 'list' (show upcoming events), 'today' (show today's events), 'clear' (remove an event by title).",
    "keywords": ["schedule", "calendar", "event", "meeting", "appointment", "remind", "today", "tomorrow", "agenda"]
}

DB_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "schedule.json")

async def load_schedule():
    import asyncio
    if not os.path.exists(DB_FILE):
        return []
    try:
        def _read():
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        return await asyncio.to_thread(_read)
    except:
        return []

async def save_schedule(data):
    import asyncio
    def _write():
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    await asyncio.to_thread(_write)

async def execute(args: dict = None) -> str:
    if not args or "action" not in args:
        return "Error: Please provide an 'action' ('add', 'list', 'today', 'clear')."
    
    action = args["action"].lower()
    schedule = await load_schedule()
    
    if action == "add":
        title = args.get("title")
        date = args.get("date", datetime.date.today().isoformat())
        time = args.get("time", "09:00")
        
        if not title:
            return "Error: Provide a 'title' for the event."
        
        event = {"title": title, "date": date, "time": time}
        schedule.append(event)
        # Sort by date then time
        schedule.sort(key=lambda e: (e["date"], e["time"]))
        await save_schedule(schedule)
        return f"Event added: '{title}' on {date} at {time}"
    
    elif action == "list":
        if not schedule:
            return "No upcoming events scheduled."
        lines = []
        for e in schedule:
            lines.append(f"- {e['date']} {e['time']} — {e['title']}")
        return "Upcoming Events:\n" + "\n".join(lines)
    
    elif action == "today":
        today = datetime.date.today().isoformat()
        today_events = [e for e in schedule if e["date"] == today]
        if not today_events:
            return "No events scheduled for today."
        lines = []
        for e in today_events:
            lines.append(f"- {e['time']} — {e['title']}")
        return f"Today's Agenda ({today}):\n" + "\n".join(lines)
    
    elif action == "clear":
        title = args.get("title", "")
        if not title:
            return "Error: Provide the 'title' of the event to clear."
        before = len(schedule)
        schedule = [e for e in schedule if e["title"].lower() != title.lower()]
        if len(schedule) < before:
            await save_schedule(schedule)
            return f"Removed event: '{title}'"
        else:
            return f"No event found with title: '{title}'"
    
    return f"Unknown action: {action}"
