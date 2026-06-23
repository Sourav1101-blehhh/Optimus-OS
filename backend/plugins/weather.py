import httpx

PLUGIN_METADATA = {
    "name": "weather",
    "description": "Gets the current weather and forecast for a specified location.",
    "keywords": ["weather", "forecast", "temperature", "rain", "sunny", "climate"]
}

async def execute(args: dict = None) -> str:
    location = args.get("location", "") if args else ""
    
    # If no location is provided, wttr.in tries to guess based on IP
    url = f"https://wttr.in/{location}?format=3"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            
        return f"Weather Report: {response.text.strip()}"
    except Exception as e:
        return f"Error fetching weather: {e}"
