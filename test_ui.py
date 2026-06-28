import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"BROWSER ERROR: {exc}"))
        
        print("Navigating to dashboard...")
        await page.goto("http://127.0.0.1:8080")
        
        # Wait for login
        await page.wait_for_selector("#login-password", state="visible")
        # Save straight to artifact directory so we can link it
        await page.screenshot(path=r"C:\Users\KIIT\.gemini\antigravity\brain\b2162bdf-4a6c-457b-98b6-f22b2ab60455\real_login.png")
        print("Login screenshot taken.")
        
        # Perform login
        print("Logging in...")
        await page.fill("#login-password", "CHANGE_ME_IN_PRODUCTION")
        await page.click("#login-btn")
        
        # Wait for dashboard to load (the vitals container or terminal scroll)
        await page.wait_for_selector(".vitals-container", state="visible", timeout=10000)
        # Give it a second to animate
        await asyncio.sleep(2)
        await page.screenshot(path=r"C:\Users\KIIT\.gemini\antigravity\brain\b2162bdf-4a6c-457b-98b6-f22b2ab60455\real_dashboard.png")
        print("Dashboard screenshot taken.")
        
        # Send a command
        print("Sending command...")
        await page.fill("#terminal-text-input", "Optimus, check system vitals and memory")
        await page.click("button[type='submit']")
        
        # Wait for a response in the terminal log
        await asyncio.sleep(5)
        await page.screenshot(path=r"C:\Users\KIIT\.gemini\antigravity\brain\b2162bdf-4a6c-457b-98b6-f22b2ab60455\real_automation.png")
        print("Automation screenshot taken.")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
