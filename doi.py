import time
import json
import re
import io
import os
import hashlib
import json
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from standardise import levenshtein
import asyncio
from seleniumbase import SB
from selenium.webdriver.chrome.options import Options
import pdfplumber
from googlesearch import search
from functools import lru_cache
from logger import print_error, print_warn, print_info, print_misc

# List of websites that block web scrapers
sites_blocking_scrappers = ["www.sciencedirect.com", "journals.biologists.com"]

# Dic of domains and times last scraped
last_scraped = {}

def get_saved_html_path(url):
    """
    Generate a file path based on a hash of the URL.
    """
    # Generate a unique filename based on the URL
    hash_url = hashlib.md5(url.encode()).hexdigest()  # Use MD5 hash for a unique identifier
    return os.path.join("html_cache", f"{hash_url}.html")

def save_html_to_file(url, html_content):
    """
    Save the HTML content to a file.
    """
    # Ensure the directory exists
    if not os.path.exists("html_cache"):
        os.makedirs("html_cache")
    
    # Generate the file path
    file_path = get_saved_html_path(url)
    
    # Save the HTML content to the file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print_misc(f"Saved HTML content to file: {file_path}")

def load_html_from_file(url):
    """
    Load the HTML content from a file if it exists.
    """
    file_path = get_saved_html_path(url)
    if os.path.exists(file_path):
        print_misc("Loading HTML from file:", file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return None

def get_url_content(url):
    """
    Fetch the HTML content from a URL.
    """
    html = load_html_from_file(url)
    if html is None and urlparse(url).hostname not in sites_blocking_scrappers:
        html = get_url_content_using_urllib(url)
    if html is None:
        print_misc(f"Trying to fetch content via browser {url}")
        time.sleep(10)
        html = asyncio.run(get_url_content_using_browser(url))
    if html is None:
        print_error(f"Failed to fetch content for {url}")
        return None
    
    save_html_to_file(url, html) # Cache the HTML content
    return html

def get_doi(url, author):
    # Extract DOI URL e.g., https://onlinelibrary.wiley.com/doi/abs/10.1111/gcb.12455 which has the 10.1111/gcb.12455 (https://doi.org/10.1111/gcb.12455)
    doi_in_url = extract_doi_from_url(url)
    if doi_in_url:
        return doi_in_url
    
    slug = url.split('/')[-1]

    html = get_url_content(url)

    dois_in_metadata = extract_doi_metadata(url)
    if dois_in_metadata and len(dois_in_metadata) == 1: # If there is only one DOI, it is likely to be correct
        return dois_in_metadata[0]

    # Parse the page for DOIs
    dois_parsed = parse_dois(html, url, author)
    dois = dois_in_metadata.extend(dois_parsed)
    if not dois:
        print_warn(f"No DOIs found in metadata or parsed HTML for {url}")
        return None
    if len(dois) == 1: # If there is only one DOI, it is likely to be correct
        return dois[0]
    for doi in dois: # If there are multiple DOIs on the page, check each one
        print_misc("Multiple DOIs:", slug, doi)
        # If part of slug in part of doi, then it is likely the correct one
        if slug in doi: # If the DOI contains the URL slug, it is likely the correct one e.g, https://www.nature.com/articles/nclimate2195 which has nclimate2195 (https://doi.org/10.1038/nclimate2195)
            return doi
        if check_doi_via_api(doi, url): # URL the DOI api to verify the URL
            return doi
        if check_doi_via_redirect(doi, url, html, author): # Check if the DOI redirects to the URL
            print_warn(f"Verified DOI via redirect: {doi} goes to {url}")
            return doi
    # Return the first DOI if none of the above conditions are met
    #return dois[0]
    

def get_doi_from_title(pub_title, author):
    # Google Search the publication's title to find what is likely the publication's url and then the DOI from that page
    print_misc(f"Publication URL is a Google Scholar URL. Publication Title: {pub_title}")

    domain = "google.com"
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 1 seconds to avoid being blocked by {domain}")
        time.sleep(1)
    last_scraped[domain] = time.time()

    results = search(pub_title)
    doi = None
    for result in results:
        print_warn(f"Getting DOI from Google Search result {result}")
        doi = get_doi(result, author)
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
    """Fetch the HTML content using urllib.request."""

    domain = urlparse(url).hostname
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 10 seconds to avoid being blocked by {domain}")
        time.sleep(10)

    last_scraped[domain] = time.time()

    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.build_opener(urllib.request.HTTPCookieProcessor()).open(req) as response:
            content_type = response.headers.get('Content-Type', '')
            content = response.read()
            if 'application/pdf' in content_type or '.pdf' in url:
                print_misc(f"Extracting text from PDF {url}")
                content = get_content_from_pdf(content, url)
                return content
            elif 'text/html' in content_type:
                content = content.decode('utf-8')
                return content
            else:
                print_error(f"Unsupported content type: {content_type}")
                return None
    except HTTPError as err:
        print_error(f"Error fetching content from {url}: {err}")
        if err.code == 403:
            site = urlparse(url).hostname
            print_warn(f"Adding {site} to sites_blocking_scrappers to prevent future attempts")
            sites_blocking_scrappers.append(site)
        return None
    except UnicodeDecodeError as e:
        print_error(f"Decode error: {e}")
        return None

@lru_cache(maxsize=1000)
async def get_url_content_using_browser(url):
    """Fetch the HTML content using SeleniumBase with undetected-chromedriver."""

    domain = urlparse(url).hostname
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 10 seconds to avoid being blocked by {domain}")
        time.sleep(10)
    last_scraped[domain] = time.time()

    try:
        # SeleniumBase configuration with stealth mode enabled
        with SB(uc=True, headless=True) as sb:  # Enables undetected Chrome in headless mode
            # Open the URL
            sb.open(url)
            time.sleep(5) # Allow page elements to load

            # If link is a pdf, extract pdf text
            if url.lower().endswith(".pdf"):
                print_misc(f"Browser: Extracting text from PDF {url}")
                pdf_bytes = sb.download_file(url)  # Download the PDF file
                if pdf_bytes:
                    return get_content_from_pdf(pdf_bytes, url)

            html = sb.get_page_source()

            return html
    except Exception as e:
        print_misc(f"[ERROR] An error occurred in get_url_content_using_browser: {e}")
        return None

def extract_doi_metadata(html):
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
    
    return []

def parse_dois(html, url, author):
    # Check rest of HTML for DOIs, note that some of these will be references to other papers and not the current paper
    pattern = r"(?:https://doi.org/[^\/])?(10.\d{4,9}/[-._()/:a-zA-Z0-9]+)"
    matches = list(set(re.findall(pattern, html, re.IGNORECASE)))
    if matches:
        print_warn(f"MIGHT BE WRONG DOI: {matches}")
        # Check to see if DOI is valid and has author name in the html
        for doi in matches:
            # If DOI ends with /full, remove it
            doi = doi.split("/full")[0]
            slug = url.split('/')[-1]
            if slug in doi:
                print_warn(f"DOI CONTAINS SLUG: {doi}")
                return [doi]
            # Remove matches that are too long to be DOIs
            if len(doi) > 60:
                print_warn(f"DOI TOO LONG ({len(doi)} characters): {doi}")
                continue
            print_warn(f"Checking DOI: {doi}")
            if not check_doi_via_api(doi, url):
                print_warn(f"Failed to verify DOI via API: {doi}")
                continue
            if not check_doi_via_redirect(doi, url, html, author): # Check if the DOI redirects to the URL
                print_warn(f"Failed to verify DOI via redirect: {doi} goes to {url}")
                continue
            # Check html contains author name
            link = get_doi_link(doi)
            print_misc(link)
            html = get_url_content(link)
            if author not in html:
                print_warn(f"Failed to verify DOI: Author not found in HTML of {link}")
                continue
            return [doi]
    return []

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
def check_doi_via_redirect(doi, expected_url, expected_html, author, attempts=1):
    if not doi:
        return False
    
    domain = 'doi.org'
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 1 second to avoid being blocked by {domain}")
        time.sleep(1)
    last_scraped[domain] = time.time()

    short_url = f"https://doi.org/{doi}"
    headers = {"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}
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
                print_misc(f"Failed to verify DOI {doi} against {expected_url}. Returning False.")
                return False
            sleep = 60*60*attempts
            print_misc(f"Sleeping for {sleep} hour")
            print_error("TODO: USE TOR TO BYPASS CAPTCHA???")
            time.sleep(sleep)
            return check_doi_via_redirect(doi, expected_url, expected_html, author, attempts+1)
        if are_urls_equal(follow_url, expected_url): # Check if the URL redirects to the expected URL
            return True
        
        if author in page_html:
            print_warn(f"Verifying DOI: '{author}' found in HTML of {doi}.")
            return True
        #if levenshtein(page_html, expected_html) < 100: # Check if the HTML content is similar
        #    print_warn(f"Verifying DOI: Similar HTML content for DOI {doi} {expected_url}")
        #    return True
    except HTTPError as err:
        print_misc(f"HTTP error {err.code} for DOI {doi}: {err.reason}")
    return False

def has_captcha(html):
    captcha_signals = ["gs_captcha_ccl", "recaptcha", "captcha-form", "rc-doscaptcha-body"]
    return any(signal in html for signal in captcha_signals)


@lru_cache(maxsize=1000)
def get_doi_api(doi):
    if not doi:
        return None
    
    domain = 'doi.org'
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 1 second to avoid being blocked by {domain}")
        time.sleep(1)
    last_scraped[domain] = time.time()

    # https://doi.org/api/handles/10.1242/jeb.243973
    api_url = f"https://doi.org/api/handles/{doi}"
    try:
        # Try loading json content from file
        data = load_html_from_file(api_url)
        if data:
            return json.loads(data)
        
        with urllib.request.urlopen(api_url) as response:
            data = json.load(response)
            # Save html content to file
            save_html_to_file(api_url, json.dumps(data, indent=4))
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
        print_misc(f"Verifying DOI: End part of DOI {doi} in link {link}")
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
    
    domain = 'shortdoi.org'
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 1 second to avoid being blocked by {domain}")
        time.sleep(1)
    last_scraped[domain] = time.time()

    # https://shortdoi.org/
    # e.g., https://shortdoi.org/10.1007/s10113-015-0832-z?format=json
    short_doi_url = f"https://shortdoi.org/{doi}?format=json"
    try:
        # Try loading json content from file
        data = load_html_from_file(short_doi_url)
        if data:
            return json.loads(data)
        
        with urllib.request.urlopen(short_doi_url) as response:
            data = json.load(response)
            # Save html content to file
            save_html_to_file(short_doi_url, json.dumps(data, indent=4))
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

