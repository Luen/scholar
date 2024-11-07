import time
from selenium import webdriver
from selenium_stealth import stealth
import undetected_chromedriver as uc
from seleniumbase import SB

# Helper function for error printing
def print_error(message):
    print(f"[ERROR] {message}")

def get_url_content_using_browser(url):
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


# Test URLs
url = "https://www.sciencedirect.com/science/article/pii/S1095643313002031"
test1 = get_url_content_using_browser(url)
test2 = get_url_content_using_seleniumbase(url)

# Displaying results for verification
print("Content from undetected Chrome driver:")
print(test1[:500] if test1 else "No content retrieved")

print("\nContent from SeleniumBase:")
print(test2[:500] if test2 else "No content retrieved")
