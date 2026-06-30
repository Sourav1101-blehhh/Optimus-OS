"""
google_mail.py — Google Workspace Gmail Plugin v5.1
===================================================
Enables full multi-turn operations, allowing Optimus to compositionally 
read and send emails via native Google Workspace APIs.
"""

import base64
from email.message import EmailMessage
from typing import Any
from googleapiclient.discovery import build

from backend.utils.google_auth import get_google_credentials

import os

PLUGIN_METADATA: dict[str, Any] = None

_creds_path = os.path.join(os.path.dirname(__file__), "..", "..", "credentials.json")
if os.path.exists(_creds_path):
    PLUGIN_METADATA = {
        "name": "google_mail",
        "description": "Reads unread emails or composes and sends new emails using the authenticated Google Workspace account.",
        "keywords": ["email", "gmail", "send", "inbox", "read", "message", "compose", "mail"],
    }

async def execute(args: dict = None) -> str:
    import asyncio
    
    if not args or "action" not in args:
        return "Error: Action must be 'read' or 'send'."
        
    action = args["action"].lower()
    
    def _run_sync():
        try:
            creds = get_google_credentials()
            service = build('gmail', 'v1', credentials=creds)
            
            if action == "read":
                limit = args.get("limit", 5)
                results = service.users().messages().list(userId='me', labelIds=['UNREAD', 'INBOX'], maxResults=limit).execute()
                messages = results.get('messages', [])
                
                if not messages:
                    return "You have no unread emails."
                    
                output = [f"Found {len(messages)} unread emails. Latest:"]
                for msg in messages:
                    txt = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['From', 'Subject']).execute()
                    headers = txt['payload']['headers']
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
                    sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown Sender")
                    output.append(f"- From: {sender}\n  Subject: {subject}")
                    
                return "\n\n".join(output)
                
            elif action == "send":
                to = args.get("to")
                subject = args.get("subject", "Message from Optimus")
                body = args.get("body", "")
                
                if not to or not body:
                    return "Error: Both 'to' and 'body' must be provided to send an email."
                    
                message = EmailMessage()
                message.set_content(body)
                message['To'] = to
                message['From'] = 'me'
                message['Subject'] = subject
                
                encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
                create_message = {'raw': encoded_message}
                
                send_message = service.users().messages().send(userId="me", body=create_message).execute()
                return f"Successfully sent email to {to}. Message ID: {send_message['id']}"
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            return f"Gmail API error: {e}"

    return await asyncio.to_thread(_run_sync)
