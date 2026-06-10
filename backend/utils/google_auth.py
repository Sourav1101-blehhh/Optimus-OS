"""
google_auth.py — Google Workspace OAuth2 Flow handler
=====================================================
Reads personal developer console parameter blocks (credentials.json)
and safely caches access tokens to data/token.json.
"""
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Scopes required for Gmail and Calendar
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.events'
]

def get_google_credentials() -> Credentials:
    """
    Handles the OAuth2 flow. Loads from token.json if available,
    otherwise reads credentials.json to prompt user login, then saves token.
    """
    root_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    data_dir = os.path.join(root_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    token_path = os.path.join(data_dir, "token.json")
    creds_path = os.path.join(root_dir, "credentials.json")
    
    creds = None
    
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}")
                creds = None
                
        if not creds:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(f"Missing {creds_path}. Please download your OAuth 2.0 Client ID JSON from GCP Console and save it as credentials.json in the project root.")
                
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            # This opens a local web server to handle the redirect
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())
            
    return creds
