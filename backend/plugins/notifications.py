from plyer import notification

PLUGIN_METADATA = {
    "name": "notifications",
    "description": "Sends a native desktop notification.",
    "keywords": ["notify", "notification", "alert", "toast", "remind"]
}

def execute(args: dict = None) -> str:
    args = args or {}
    title = args.get("title", "Optimus OS")
    message = args.get("message", "You have a new notification.")
    
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="Optimus OS",
            timeout=5
        )
        return f"Notification sent: {title} - {message}"
    except Exception as e:
        return f"Failed to send notification: {e}"
