import time
import json
import re
import io
import os
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from standardise import levenshtein
import asyncio
from playwright.async_api import async_playwright
import pdfplumber
from googlesearch import search
from functools import lru_cache
from logger import print_error, print_warn, print_info

def get_doi(url):
    # Extract DOI URL e.g., https://onlinelibrary.wiley.com/doi/abs/10.1111/gcb.12455 which has the 10.1111/gcb.12455 (https://doi.org/10.1111/gcb.12455)
    doi_in_url = extract_doi_from_url(url)
    if doi_in_url:
        return doi_in_url
    
    slug = url.split('/')[-1]
    html = None
    html = get_url_content_using_urllib(url)
    if html is None:
        print(f"Trying to fetch content via browser {url}")
        time.sleep(10)
        html = asyncio.run(get_url_content_using_browser(url))
    if html is None:
        print_error(f"Failed to fetch content for {url}")
        return None

    # Parse the page for DOIs
    dois = parse_dois(html)

    if dois:
        if len(dois) == 1: # If there is only one DOI, it is likely to be correct
            return dois[0]
        for doi in dois: # If there are multiple DOIs on the page, check each one
            print("Multiple DOIs:", slug, doi)
            # If part of slug in part of doi, then it is likely the correct one
            if slug in doi: # If the DOI contains the URL slug, it is likely the correct one e.g, https://www.nature.com/articles/nclimate2195 which has nclimate2195 (https://doi.org/10.1038/nclimate2195)
                return doi
            if check_doi_via_api(doi, url): # URL the DOI api to verify the URL
               time.sleep(1)
               return doi
            if check_doi_via_redirect(doi, url, html): # Check if the DOI redirects to the URL
                time.sleep(1)
                print_warn(f"Verified DOI via redirect: {doi} goes to {url}")
                return doi
        # Return the first DOI if none of the above conditions are met
        #return dois[0]
    
    return None


def get_doi_from_title(pub_title):
    # Google Search the publication's title to find what is likely the publication's url and then the DOI from that page
    print(f"Publication URL is a Google Scholar URL. Publication Title: {pub_title}")
    results = search(pub_title)
    doi = None
    for result in results:
        print_warn(f"Getting DOI from Google Search result {result}")
        doi = get_doi(result, pub_title)
        if doi:
            return doi
    return None

def get_content_from_pdf(pdf_bytes, url):
    try:
        pdf_file = io.BytesIO(pdf_bytes)
        with pdfplumber.open(pdf_file) as pdf:
            # get page from url hash - e.g., https://repository.library.noaa.gov/view/noaa/42440/noaa_42440_DS1.pdf#page=124
            page_num = url.split("#page=")[-1] if "#page=" in url else None
            if page_num:
                if not page_num.isdigit():
                    print_warn(f"Invalid page number: {page_num}")
                try:
                    target_page = pdf.pages[int(page_num) - 1]  # Convert page number from 1-based to 0-based index
                    return target_page.extract_text()
                except IndexError:
                    print_warn(f"Page {page_num} not found in PDF")
            
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + " "
            return text.strip()
    except Exception as e:
        print_error(f"An error occurred while extracting text from PDF: {e}")
        return None

@lru_cache(maxsize=1000)
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
                print_error(f"Unsupported content type: {content_type}")
                return None
    except HTTPError as err:
        print_error(f"Error fetching content from {url}: {err}")
        return None
    except UnicodeDecodeError as e:
        print_error(f"Decode error: {e}")
        return None

@lru_cache(maxsize=1000)
async def get_url_content_using_browser(url):
    browser = None  # Ensure the browser variable is accessible for the finally block
    try:
        async with async_playwright() as p:
            # Launch the browser in headless mode
            # Note that some websites may block headless browsers e.g., https://www.sciencedirect.com/science/article/pii/S1095643313002031
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-infobars',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extension',
                    '--window-position=0,0',
                    '--ignore-certificate-errors',
                    '--ignore-certificate-errors-spki-list'
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 1280},
                accept_downloads=True, # Enables download in the context (for PDFs)
            )
            page = await context.new_page()

            # Modify WebGL and Navigator properties to avoid detection
            await page.add_init_script("""
            navigator.webdriver = false;
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'NVIDIA Corporation';
                }
                if (parameter === 37446) {
                    return 'NVIDIA GeForce GTX 660/PCIe/SSE2';
                }
                return getParameter(parameter);
            };
            """)


            # If link is a pdf, extract pdf text
            if ".pdf" in url:
                print(f"Browser: Extracting text from PDF {url}")
                # https://github.com/microsoft/playwright/issues/12777
                temp_file_name = "temp.html"
                temp_html = f"""<html><body><a href="{url}">{url}</a></body></html>"""
                
                file = os.path.realpath(__file__)
                temp_dir = os.path.join(os.path.dirname(file), "temp")
                
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir)
                
                temp_html_path = os.path.join(temp_dir, temp_file_name)
                
                # Write the HTML to a temporary file
                with open(temp_html_path, 'w', encoding='utf8') as f:
                    f.write(temp_html)
                
                await page.goto("file://" + temp_html_path)
                link = await page.query_selector('//a')
                url = await link.get_attribute('href')
                
                # Download the PDF
                async with page.expect_download() as download_info:
                    await link.click(modifiers=["Alt"])
                
                download = await download_info.value

                temp_pdf_path = os.path.join(temp_dir, download.suggested_filename)
                await download.save_as(temp_pdf_path)               

                # Read the PDF
                with open(temp_pdf_path, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()
                
                # Clean up
                os.remove(temp_html_path)
                os.remove(temp_pdf_path)
                # If directory is empty, remove it
                if not os.listdir(temp_dir):
                    os.rmdir(temp_dir)

                return get_content_from_pdf(pdf_bytes, url)

            # Navigate to the page
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=60000) # wait_until="load" or "domcontentloaded"
            except Exception as e:
                #await page.screenshot(path='fail1.png')
                print_error(f"get_url_content_using_browser() An error occurred: {e}, retrying in 60 seconds")
                time.sleep(60)
                response = await page.goto(url, wait_until="networkidle", timeout=60000) # wait_until="load" or "domcontentloaded"

            if response and not response.ok:
                #await page.screenshot(path='fail2.png')
                print_error(f"Failed to load the page, status: {response.status}")
                return None
        
            # Sleep for 1 second
            await asyncio.sleep(1)

            #await page.screenshot(path='fail3.png')
            # Get the page content
            # html = await page.content()
            # Render Page Content
            html = await page.evaluate('document.body.innerHTML')

            return html
    except Exception as e:
        print_error(f"get_url_content_using_browser() An error occurred: {e}")
        return None
    finally:
        if browser:
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
    
    # Check HTML for DOIs a tag with class doi e.g., a.doi on https://www.sciencedirect.com/science/article/abs/pii/S1095643313002031
    pattern = r'<a[^>]*class="[^"]*doi[^"]*"[^>]*href="https://doi.org/([^"]+)"'
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
    parsed_url = urlparse(url)
    # Remove query and fragment parts
    normalized_url = parsed_url._replace(query='', fragment='').geturl()
    normalized_url = normalized_url.rstrip('/')
    for old, new in replacements.items():
        normalized_url = normalized_url.replace(old, new)
    return normalized_url

def are_urls_equal(url1, url2): 
    if normalise_url(url1) == normalise_url(url2):
        return True
    
    # Extract hostnames and paths
    parsed_url1 = urlparse(url1)
    parsed_url2 = urlparse(url2)
    
    # Check if hostnames are the same
    if parsed_url1.hostname == parsed_url2.hostname:
        # Compare the last two parts of the path
        last_two_parts1 = "/".join(parsed_url1.path.strip('/').split("/")[-2:])
        last_two_parts2 = "/".join(parsed_url2.path.strip('/').split("/")[-2:])
        if last_two_parts1 == last_two_parts2:
            return True
        replacements = {
            "/article-abstract": "/article",
            "/article-lookup": "/article",
        }
        first_two_parts1 = "/".join(parsed_url1.path.strip('/').split("/")[:2])
        first_two_parts2 = "/".join(parsed_url2.path.strip('/').split("/")[:2])
        for old, new in replacements.items():
            first_two_parts1 = first_two_parts1.replace(old, new)
            first_two_parts2 = first_two_parts2.replace(old, new)
        if first_two_parts1 == first_two_parts2:
            print_warn(f"Possible URL Match: {url1} {url2}")
            return True
        return True
    
    return False

def extract_doi_from_url(url):
    # Regex pattern to find DOI in URL
    # DOI starts with 10 and can contain digits or dots, followed by a slash and a character sequence
    #doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+'
    # https://journals.biologists.com/jeb/article-pdf/doi/10.1242/jeb.243973/2170187/jeb243973.pdf
    # https://www.frontiersin.org/articles/10.3389/fmars.2021.724913/full?trk=public_post_comment-text
    # doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+(?![.][a-z]+)'
    doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+?(?=/|$|\.pdf)'
    match = re.search(doi_pattern, url, re.IGNORECASE)
    if match and check_doi_via_api(match.group(), url): # Check if DOI is valid e.g., 10.1242/jeb.243973
        return match.group()
    
    # https://academic.oup.com/conphys/article-pdf/doi/10.1093/conphys/cox003/17644168/cox003.pdf
    # try adding one more slash to get 10.1093/conphys/cox003
    doi_pattern_extended = r'10\.\d{4,9}/[-._;():A-Z0-9]+/[-._;():A-Z0-9]+'
    match = re.search(doi_pattern_extended, url, re.IGNORECASE)
    if match and check_doi_via_api(match.group(), url):
        return match.group()
    
    doi_pattern_full = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+'
    #doi_pattern_full = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+(?=[.][a-z]+)'
    match = re.search(doi_pattern_full, url, re.IGNORECASE)
    if match and check_doi_via_api(match.group(), url):
        return match.group()

    return None

@lru_cache(maxsize=1000)
def check_doi_via_redirect(doi, expected_url, expected_html, attempts=1):
    if not doi:
        return False
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
            print_warn(f"Captcha encountered on {doi} attempt {attempts}")
            if attempts > 3:
                print(f"Failed to verify DOI {doi} against {expected_url}. Returning False.")
                return False
            sleep = 60*60*attempts
            print(f"Sleeping for {sleep} hour")
            time.sleep(sleep)
            return check_doi_via_redirect(doi, expected_url, expected_html, attempts+1)
        if are_urls_equal(follow_url, expected_url): # Check if the URL redirects to the expected URL
            return True
        if "Rummer" in page_html:
            print_warn(f"Verifying DOI: 'Rummer' found in HTML of {doi}. Expected URL: {expected_url}")
            return True
        if levenshtein(page_html, expected_html) < 100: # Check if the HTML content is similar
            print_warn(f"Verifying DOI: Similar HTML content for DOI {doi} {expected_url}")
            return True
    except HTTPError as err:
        print(f"HTTP error {err.code} for DOI {doi}: {err.reason}")
    return False

def has_captcha(html):
    captcha_signals = ["gs_captcha_ccl", "recaptcha", "captcha-form", "rc-doscaptcha-body"]
    return any(signal in html for signal in captcha_signals)


@lru_cache(maxsize=1000)
def get_doi_api(doi):
    if not doi:
        return None
    # https://doi.org/api/handles/10.1242/jeb.243973
    api_url = f"https://doi.org/api/handles/{doi}"
    try:
        with urllib.request.urlopen(api_url) as response:
            data = json.load(response)
            time.sleep(1)
            return data
    except HTTPError as err:
        print_error(f"HTTP error {err.code} for DOI {doi}: {err.reason}")
        return None

def get_doi_resolved_link(doi):
    if not doi:
        return None
    data = get_doi_api(doi)
    if not data:
        return None
    link = None
    try:
        for value in data["values"]:
            if value["type"] == "URL":
                link = value["data"]["value"]
    except Exception as e:
        print_error(f"Failed to get resolved link for DOI {doi}: {e}")
    return link


# Verify the DOI against the URL
def check_doi_via_api(doi, expected_url):
    if not doi or not expected_url:
        return None
    link = get_doi_resolved_link(doi)
    if not link:
        return None
    if are_urls_equal(link, expected_url):
        return True
    # check end part of doi to see if it's in the new url
    # e.g., 10.1242/jeb.243973 in https://journals.biologists.com/jeb/article/225/22/jeb243973/283144/Escape-response-kinematics-in-two-species-of
    if doi.split("/")[-1] in link or doi.split(".")[-1] in link:
        print(f"Verifying DOI: End part of DOI {doi} in link {link}")
        return True
    print_error (f"Failed to verify DOI {doi}: {link} against {expected_url}")
    return False

def get_doi_link(doi):
    if not doi:
        return None
    link = get_doi_resolved_link(doi)
    if link:
        return "https://doi.org/" + doi
    return None

@lru_cache(maxsize=1000)
def get_doi_short_api(doi):
    if not doi:
        return None
    # https://shortdoi.org/
    # e.g., https://shortdoi.org/10.1007/s10113-015-0832-z?format=json
    short_doi_url = f"https://shortdoi.org/{doi}?format=json"
    try:
        with urllib.request.urlopen(short_doi_url) as response:
            data = json.load(response)
            return data
    except HTTPError as err:
        print_error(f"HTTP error {err.code} for short DOI {doi}: {err.reason}")
        return None
    except URLError as e:
        print_error(f"URL error {e.reason}")
        return None
    except Exception as e:
        print_error(f"get_doi_short_api() An error occurred: {e}")
        return None


def get_doi_short(doi):
    if not doi:
        return None
    data = get_doi_short_api(doi)
    if data:
        return data["ShortDOI"]
    return None

def get_doi_short_link(doi_short):
    if not doi_short:
        return None
    return "https://doi.org/" + doi_short

