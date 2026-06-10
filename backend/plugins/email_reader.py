import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv

load_dotenv()

PLUGIN_METADATA = {
    "name": "email_reader",
    "description": "Reads unread emails from the configured IMAP email account.",
    "keywords": ["email", "mail", "inbox", "messages", "read email"]
}

def execute(args: dict = None) -> str:
    username = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    imap_url = os.getenv("IMAP_SERVER", "imap.gmail.com")
    
    if not username or not password or username == "your_email@gmail.com":
        return "Error: Email credentials are not configured in the .env file."
        
    try:
        # Connect to the server
        mail = imaplib.IMAP4_SSL(imap_url)
        mail.login(username, password)
        mail.select("inbox")
        
        # Search for unread emails
        status, messages = mail.search(None, "UNSEEN")
        
        if status != "OK":
            return "Error searching for emails."
            
        email_ids = messages[0].split()
        
        if not email_ids:
            return "You have no unread emails."
            
        limit = args.get("limit", 5) if args else 5
        output = [f"You have {len(email_ids)} unread emails. Here are the latest {min(len(email_ids), limit)}:"]
        
        # Fetch latest unread emails (reverse order)
        for e_id in reversed(email_ids[-limit:]):
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    
                    sender = msg.get("From")
                    output.append(f"- From: {sender}\n  Subject: {subject}")
                    
        mail.logout()
        return "\n\n".join(output)
        
    except Exception as e:
        return f"Error reading emails: {e}"
