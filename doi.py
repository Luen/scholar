import time
import json
import re
import io
import urllib.request
from urllib.error import HTTPError, URLError
from standardise import levenshtein
import asyncio
from playwright.async_api import async_playwright
import pdfplumber


def get_doi(url):
    # Extract DOI URL e.g., https://onlinelibrary.wiley.com/doi/abs/10.1111/gcb.12455 which has the 10.1111/gcb.12455 (https://doi.org/10.1111/gcb.12455)
    doi_in_url = extract_doi_from_url(url)
    if doi_in_url:
        return doi_in_url
    
    # e.g., https://scholar.google.com/scholar?cluster=4186906934658759747&hl=en&oi=scholarr
    if "scholar.google.com" in url:
        print("Google Scholar URL, so not expecting a DOI. Skipping")
        return None
    
    slug = url.split('/')[-1]
    html = get_url_content_using_urllib(url)
    if html is None:
        print(f"Trying to fetch content via browser {url}")
        html = asyncio.run(get_url_content_using_browser(url))
    if html is None:
        return None
    
    dois = parse_dois(html) # Parse the page for DOIs

    if dois:
        if len(dois) == 1: # If there is only one DOI, return it
            return dois[0]
        for doi in dois: # If there are multiple DOIs on the page, check each one
            print(slug, doi)
            # If part of slug in part of doi, then it is likely the correct one
            if slug in doi: # If the DOI contains the URL slug, it is likely the correct one e.g, https://www.nature.com/articles/nclimate2195 which has nclimate2195 (https://doi.org/10.1038/nclimate2195)
                return doi
            if check_doi_via_api(doi, url): # URL the DOI api to verify the URL
               return doi
            if check_doi_via_redirect(doi, url, html): # Check if the DOI redirects to the URL
                return doi
        return dois[0]

    return None

def get_content_from_pdf(pdf_bytes, url):
    try:
        pdf_file = io.BytesIO(pdf_bytes)
        with pdfplumber.open(pdf_file) as pdf:
            # get page from url hash - e.g., https://repository.library.noaa.gov/view/noaa/42440/noaa_42440_DS1.pdf#page=124
            page_num = url.split("#page=")[-1] if "#page=" in url else None
            if page_num:
                if not page_num.isdigit():
                    print(f"Invalid page number: {page_num}")
                    return None
                try:
                    target_page = pdf.pages[int(page_num) - 1]  # Convert page number from 1-based to 0-based index
                    return target_page.extract_text()
                except IndexError:
                    print(f"Page {page_num} not found in PDF")
                    return None
            else:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text()
                return text
    except Exception as e:
        print(f"An error occurred while extracting text from PDF: {e}")
        return None
    
def get_url_content_using_urllib(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.build_opener(urllib.request.HTTPCookieProcessor()).open(req) as response:
            content_type = response.headers.get('Content-Type', '')
            content = response.read()
            if 'application/pdf' in content_type or '.pdf' in url:
                print(f"Extracting text from PDF {url}")
                return get_content_from_pdf(content, url)
            elif 'text/html' in content_type:
                return content.decode('utf-8')
            else:
                print(f"Unsupported content type: {content_type}")
                return None
    except HTTPError as err:
        print(f"Error fetching content from {url}: {err}")
        return None
    except UnicodeDecodeError as e:
        print(f"Decode error: {e}")
        return None

async def get_url_content_using_browser(url):
    try:
        async with async_playwright() as p:
            # Launch the browser
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Navigate to the page
            await page.goto(url, wait_until="load")

            # Get the page content
            html = await page.content()
            return html
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    finally:
        await browser.close()

def parse_dois(html):
    if html is None:
        return []
    #<meta name="prism.doi" content="doi:10.1038/nclimate2195"/>
    #<meta name="dc.identifier" content="doi:10.1038/nclimate2195"/>
    #<meta name="DOI" content="10.1038/nclimate2195"/>
    #<meta name="citation_doi" content="10.1038/nclimate2195"/>
    #pattern = r'<meta name="[^"]*doi[^"]*" content="doi:?(10.\d{4,9}/[-._()/:A-Z0-9]+)"'
    #pattern = r'<meta name="[^"]*doi[^"]*" content="doi:?(10\.\d{4,9}/[-._()/:A-Z0-9]+)"'

    # Check HTML meta tags for DOIs
    pattern = r'<meta name=\".*\" content=\"(?:doi:)?(10\.\d{4,9}/[-._()/:a-zA-Z0-9]+)\"'
    matches = list(set(re.findall(pattern, html, re.IGNORECASE)))
    if matches:
        return matches

    # Check rest of HTML for dois
    pattern = r"(?:https://doi.org/[^\/])?(10.\d{4,9}/[-._()/:a-zA-Z0-9]+)"
    return list(set(re.findall(pattern, html, re.IGNORECASE)))

def normalise_url(url):
    replacements = {
        "/abs/": "/",
        "/article/": "/",
        "/articles/": "/",
        "http://": "https://",
        "//www.": "//"
    }
    for old, new in replacements.items():
        url = url.replace(old, new)
    return url.split("?")[0]


def extract_doi_from_url(url):
    # Regex pattern to find DOI in URL
    # DOI starts with 10 and can contain digits or dots, followed by a slash and a character sequence
    #doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+'
    # https://journals.biologists.com/jeb/article-pdf/doi/10.1242/jeb.243973/2170187/jeb243973.pdf
    doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+(?![.][a-z]+)'
    match = re.search(doi_pattern, url, re.IGNORECASE)

    if match:
        return match.group()
    else:
        return None

# Verify the DOI against the URL
def check_doi_via_api(doi, expected_url):
    api_url = f"https://doi.org/api/handles/{doi}"
    try:
        with urllib.request.urlopen(api_url) as response:
            data = json.load(response)
            time.sleep(1)
            for value in data["values"]: # Example json https://doi.org/api/handles/10.1038/nclimate2195
                if value["type"] == "URL" and normalise_url(value["data"]["value"]) == normalise_url(expected_url):
                    return True
    except Exception as e:
        # Extract URL if possible from the data dictionary regardless of the error location
        url = None
        for value in data.get("values", []):  # Safely iterate with a default empty list if data is not initialized
            if value["type"] == "URL":
                url = value["data"]["value"]
                break  # Break after finding the first URL, assuming only one is needed for the log
        print(f"Failed to verify DOI {doi}. Retrieved URL {url} does not match the expected URL {expected_url}: {e}")

    return False

def check_doi_via_redirect(doi, expected_url, expected_html, attempts=1):
    short_url = f"https://doi.org/{doi}"
    headers = {"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}
    time.sleep(30)
    req = urllib.request.Request(short_url, headers=headers)
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        response = opener.open(req, timeout=100)
        follow_url = response.geturl()
        page_html = response.read().decode('utf-8')
        response.close()
        if has_captcha(page_html):
            print(f"Captcha encountered on {doi} attempt {attempts}")
            if attempts > 3:
                print(f"Failed to verify DOI {doi} against {expected_url}. Returning False.")
                return False
            sleep = 60*60*attempts
            print(f"Sleeping for {sleep} hour")
            time.sleep(sleep)
            return check_doi_via_redirect(doi, expected_url, expected_html, attempts+1)
        if normalise_url(follow_url) == normalise_url(expected_url): # Check if the URL redirects to the expected URL
            return True
        if levenshtein(response.read(), expected_html) < 100: # Check if the HTML content is similar
            return True
    except HTTPError as err:
        print(f"HTTP error {err.code} for DOI {doi}: {err.reason}")
    return False

def has_captcha(html):
    captcha_signals = ["gs_captcha_ccl", "recaptcha", "captcha-form", "rc-doscaptcha-body"]
    return any(signal in html for signal in captcha_signals)


def shortDOI(doi):
    # also see this service - http://shortdoi.org/
    # e.g., http://shortdoi.org/10.1007/s10113-015-0832-z?format=json

    BASE_URL = "https://doi.org/"
    # shortUrl= doi if doi.startswith(BASE_URL) else BASE_URL+doi
    shortDOI = doi.replace(BASE_URL, "")
    return shortDOI
