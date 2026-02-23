import asyncio
from playwright.async_api import async_playwright
from agent_visualizer.visualizer import AgentVisualizer


async def run_agent():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Step 1: Open Google
        await page.goto("https://www.google.com")

        await page.fill("textarea[name='q']", "Playwright Python tutorial")
        await page.keyboard.press("Enter")

        await page.wait_for_timeout(2000)

        await page.click("h3")

        await page.wait_for_timeout(3000)
        await browser.close()


if __name__ == "__main__":
    with AgentVisualizer() as visualizer:
        print("Live View URL:", visualizer.get_live_view_url())
        asyncio.run(run_agent())