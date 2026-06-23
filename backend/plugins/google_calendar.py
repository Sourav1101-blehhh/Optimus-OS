"""
google_calendar.py — Google Workspace Calendar Plugin v5.1
==========================================================
Enables full multi-turn operations, allowing Optimus to compositionally 
read and sync events natively with Google Calendar API.
"""

import datetime
from typing import Any
from googleapiclient.discovery import build

from backend.utils.google_auth import get_google_credentials

PLUGIN_METADATA: dict[str, Any] = {
    "name": "google_calendar",
    "description": "Reads upcoming events or adds new events to Google Calendar.",
    "keywords": ["calendar", "schedule", "meeting", "event", "agenda", "google calendar", "appointment"],
}

async def execute(args: dict = None) -> str:
    import asyncio
    
    if not args or "action" not in args:
        return "Error: Action must be 'list' or 'add'."
        
    action = args["action"].lower()
    
    def _run_sync():
        try:
            creds = get_google_credentials()
            service = build('calendar', 'v3', credentials=creds)
            
            if action == "list":
                # Call the Calendar API
                now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
                limit = args.get("limit", 10)
                events_result = service.events().list(calendarId='primary', timeMin=now,
                                                      maxResults=limit, singleEvents=True,
                                                      orderBy='startTime').execute()
                events = events_result.get('items', [])

                if not events:
                    return 'No upcoming events found in Google Calendar.'
                    
                output = ["Upcoming events:"]
                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    # clean up the ISO format string for basic reading
                    clean_time = start.replace("T", " ")[:16]
                    output.append(f"- {clean_time}: {event['summary']}")
                    
                return "\n".join(output)
                
            elif action == "add":
                summary = args.get("summary")
                start_time_str = args.get("start_time") # Format: 2026-06-10T09:00:00-07:00
                end_time_str = args.get("end_time")
                
                if not summary or not start_time_str or not end_time_str:
                    return "Error: 'summary', 'start_time', and 'end_time' are required to add an event."
                    
                event = {
                  'summary': summary,
                  'start': {
                    'dateTime': start_time_str,
                    'timeZone': 'UTC',
                  },
                  'end': {
                    'dateTime': end_time_str,
                    'timeZone': 'UTC',
                  },
                }

                event_result = service.events().insert(calendarId='primary', body=event).execute()
                return f"Event created: {event_result.get('htmlLink')}"
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            return f"Google Calendar API error: {e}"

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run_sync), timeout=15.0)
    except asyncio.TimeoutError:
        return "Error: Google Calendar API request timed out."
