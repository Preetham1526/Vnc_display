import asyncio
from playwright.async_api import async_playwright

async def run_smart_agent():
    async with async_playwright() as p:
        # CRITICAL: headless=False is required to show actions in VNC
        browser = await p.chromium.launch(headless=False)
        
        # Set viewport to match your Xvfb resolution
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        # Your AI logic here
        print("Agent Smart is starting actions...")
        await page.goto("https://www.google.com")
        await page.fill('textarea[name="q"]', "AI Agents in production")
        await page.press('textarea[name="q"]', "Enter")
        
        # Keep the browser open so you can watch it
        await asyncio.sleep(1000) 

if __name__ == "__main__":
    asyncio.run(run_smart_agent())