import webbrowser

PLUGIN_METADATA = {
    "name": "browser",
    "description": "Opens a given URL in the default web browser.",
    "keywords": ["browser", "open", "url", "website", "chrome", "edge"]
}

def execute(args: dict = None) -> str:
    if not args or "url" not in args:
        return "Error: No URL provided."
    
    url = args["url"]
    
    # Ensure it has a scheme
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
        
    try:
        webbrowser.open(url)
        return f"Successfully opened {url} in the default browser."
    except Exception as e:
        return f"Error opening URL: {e}"
