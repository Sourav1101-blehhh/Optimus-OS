import asyncio
from playwright.async_api import async_playwright

PLUGIN_METADATA = {
    "name": "browser",
    "description": "Uses Playwright to navigate a webpage in a headless browser, click elements, or extract text.",
    "keywords": ["browser", "open", "url", "website", "scrape", "extract"]
}

async def execute(args: dict = None) -> str:
    if not args or "url" not in args:
        return "Error: No URL provided."
    
    url = args["url"]
    if not url.startswith("http"):
        url = "https://" + url
        
    action = args.get("action", "extract_text")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=15000)
            
            if action == "extract_text":
                text = await page.evaluate("document.body.innerText")
                await browser.close()
                truncated = "..." if len(text) > 2000 else ""
                return f"Successfully extracted text from {url}:\n\n{text[:2000]}{truncated}"
            else:
                await browser.close()
                return f"Successfully opened {url}"
    except Exception as e:
        return f"Error with Playwright browser: {e}"
