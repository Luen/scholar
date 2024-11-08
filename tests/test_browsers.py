import time
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from selenium import webdriver
from selenium_stealth import stealth
import undetected_chromedriver as uc
from seleniumbase import SB

# Helper function for error printing
def print_error(message):
    print(f"[ERROR] {message}")

async def get_url_content_using_playwrightstealth(url):
    """
    Fetch the HTML content using Playwright with stealth mode enabled.
    """
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
            )
            page = await context.new_page()
            
            # Apply stealth mode
            await stealth_async(page)

            # Attempt to navigate to the URL
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=60000)
                if response and not response.ok:
                    print_error(f"Failed to load the page, status: {response.status}")
                    return None
            except Exception as e:
                print_error(f"An error occurred during navigation: {e}")
                return None

            # Extract the page content
            html = await page.content()
            return html
    except Exception as e:
        print_error(f"Error in browser fetch: {e}")
        return None
    finally:
        if browser:
            await browser.close()

def get_url_content_using_undetectedchromedriver(url):
    """
    Fetch the HTML content using Selenium with undetected-chromedriver and stealth mode enabled.
    """
    try:
        # Initialize undetected Chrome driver
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")  # Run in headless mode
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Use undetected Chrome driver with stealth settings
        driver = uc.Chrome(options=options)
        
        # Apply stealth settings to bypass detection
        stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True)
        
        # Navigate to the URL
        driver.get(url)
        time.sleep(2)  # Wait for the page to load

        # Extract HTML content
        html = driver.page_source
        return html
    except Exception as e:
        print_error(f"Error in Selenium fetch: {e}")
        return None
    finally:
        driver.quit()


def get_url_content_using_seleniumbase(url):
    """
    Fetch the HTML content using SeleniumBase with undetected-chromedriver enabled.
    """
    try:
        with SB(uc=True, headless=True) as sb:  # Enables undetected_chromedriver
            sb.open(url)
            html = sb.get_page_source()
            return html
    except Exception as e:
        print_error(f"Error with SeleniumBase fetch: {e}")
        return None


async def main():
    # Test URL
    url = "https://www.sciencedirect.com/science/article/pii/S1095643313002031"

    # Asynchronously fetch content using Playwright
    test1 = await get_url_content_using_playwrightstealth(url)
    test2 = get_url_content_using_undetectedchromedriver(url)
    test3 = get_url_content_using_seleniumbase(url)

    # Displaying results for verification
    print("Content from Playwright with stealth mode:")
    print(test1[:500] if test1 else "FAILED to retrieve content")
    print("-------------------")
    print("Content from undetected Chrome driver:")
    print(test2[:500] if test2 else "FAILED to retrieve content")
    print("-------------------")
    print("\nContent from SeleniumBase:")
    print(test3[:500] if test3 else "FAILED to retrieve content")

# Run the main function
asyncio.run(main())