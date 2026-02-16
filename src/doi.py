import io
import os
import re
import time
from functools import lru_cache
from urllib.parse import urlparse

import pdfplumber
import requests
from googlesearch import search

from .logger import print_error, print_info, print_misc, print_warn

# Hero scraper HTTP API URL (Ulixee Hero browser)
HERO_SCRAPER_URL = os.environ.get("HERO_SCRAPER_URL", "http://localhost:3000")

# List of websites that block web scrapers
sites_blocking_scrappers = ["www.sciencedirect.com", "journals.biologists.com"]

# Dic of domains and times last scraped
last_scraped = {}


def get_url_content(url):
    """
    Fetch the HTML content from a URL. Uses requests-cache for caching.
    """
    if urlparse(url).hostname not in sites_blocking_scrappers:
        html = get_url_content_using_requests(url)
    else:
        html = None
    if html is None:
        print_misc(f"Trying to fetch content via Hero browser {url}")
        time.sleep(10)
        html = get_url_content_using_browser(url)
    if html is None:
        print_error(f"Failed to fetch content for {url}")
        return None
    return html


def get_doi(url, author):
    """Get DOI from URL or page content."""
    # First try to extract DOI from URL
    doi = extract_doi_from_url(url)
    if doi:
        print_info(f"Found DOI in URL: {doi}")
        return doi

    # Then try to get it from page content
    html = get_url_content(url)
    if not html:
        return None

    # Try to get DOI from metadata
    dois_in_metadata = extract_doi_metadata(html)
    if dois_in_metadata:
        if len(dois_in_metadata) == 1:
            print_info(f"Found single DOI in metadata: {dois_in_metadata[0]}")
            return dois_in_metadata[0]

        # If multiple DOIs found, try to find the most relevant one
        for doi in dois_in_metadata:
            if check_doi_via_api(doi, url):
                print_info(f"Verified DOI via API: {doi}")
                return doi

    # Parse the page for DOIs
    dois_parsed = parse_dois(html, url, author)
    if dois_parsed:
        for doi in dois_parsed:
            if check_doi_via_api(doi, url):
                print_info(f"Verified DOI via API: {doi}")
                return doi

    print_warn(f"No verified DOI found for {url}")
    return None


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
        # Handle both string and bytes input
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode("utf-8")

        pdf_file = io.BytesIO(pdf_bytes)
        with pdfplumber.open(pdf_file) as pdf:
            # get page from url hash - e.g., https://repository.library.noaa.gov/view/noaa/42440/noaa_42440_DS1.pdf#page=124
            page_num = url.split("#page=")[-1] if "#page=" in url else None
            if page_num:
                if not page_num.isdigit():
                    print_warn(f"Invalid page number: {page_num}")
                try:
                    target_page = pdf.pages[
                        int(page_num) - 1
                    ]  # Convert page number from 1-based to 0-based index
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
def get_url_content_using_requests(url):
    """Fetch the HTML content using requests (cached via requests-cache)."""

    domain = urlparse(url).hostname
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 10 seconds to avoid being blocked by {domain}")
        time.sleep(10)

    last_scraped[domain] = time.time()

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")

        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            print_misc(f"Extracting text from PDF {url}")
            return get_content_from_pdf(resp.content, url)
        if "text/html" in content_type:
            return resp.text

        print_error(f"Unsupported content type: {content_type}")
        return None
    except requests.HTTPError as err:
        print_error(f"Error fetching content from {url}: {err}")
        if err.response is not None and err.response.status_code == 403:
            site = urlparse(url).hostname
            print_warn(f"Adding {site} to sites_blocking_scrappers to prevent future attempts")
            sites_blocking_scrappers.append(site)
        return None
    except requests.RequestException as e:
        print_error(f"Request error: {e}")
        return None


@lru_cache(maxsize=1000)
def get_url_content_using_browser(url):
    """Fetch the HTML content using Ulixee Hero via the hero-scraper HTTP API."""

    domain = urlparse(url).hostname
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 10 seconds to avoid being blocked by {domain}")
        time.sleep(10)
    last_scraped[domain] = time.time()

    try:
        if url.lower().endswith(".pdf"):
            print_misc(f"Browser: Extracting text from PDF {url}")
            try:
                resp = requests.get(url, timeout=60)
                resp.raise_for_status()
                if resp.content:
                    return get_content_from_pdf(resp.content, url)
            except requests.RequestException as e:
                print_error(f"Error downloading PDF: {e}")
                return None

        scrape_url = f"{HERO_SCRAPER_URL.rstrip('/')}/scrape"
        resp = requests.post(scrape_url, json={"url": url}, timeout=90)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print_misc(f"[ERROR] Hero scraper request failed: {e}")
        return None
    except Exception as e:
        print_misc(f"[ERROR] An error occurred in get_url_content_using_browser: {e}")
        return None


def extract_doi_metadata(html):
    if html is None:
        return []

    # <meta name="prism.doi" content="doi:10.1038/nclimate2195"/>
    # <meta name="dc.identifier" content="doi:10.1038/nclimate2195"/>
    # <meta name="DOI" content="10.1038/nclimate2195"/>
    # <meta name="citation_doi" content="10.1038/nclimate2195"/>
    # pattern = r'<meta name="[^"]*doi[^"]*" content="doi:?(10.\d{4,9}/[-._()/:A-Z0-9]+)"'
    # pattern = r'<meta name="[^"]*doi[^"]*" content="doi:?(10\.\d{4,9}/[-._()/:A-Z0-9]+)"'

    # Check HTML meta tags for DOIs
    pattern = r"<meta name=\".*\" content=\"(?:doi:)?(10\.\d{4,9}/[-._()/:a-zA-Z0-9]+)\""
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
            slug = url.split("/")[-1]
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
            if not check_doi_via_redirect(
                doi, url, html, author
            ):  # Check if the DOI redirects to the URL
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
        "//www.": "//",
    }
    parsed_url = urlparse(url)
    # Remove query and fragment parts
    normalized_url = parsed_url._replace(query="", fragment="").geturl()
    normalized_url = normalized_url.rstrip("/")
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
        last_two_parts1 = "/".join(parsed_url1.path.strip("/").split("/")[-2:])
        last_two_parts2 = "/".join(parsed_url2.path.strip("/").split("/")[-2:])
        if last_two_parts1 == last_two_parts2:
            return True
        replacements = {
            "/article-abstract": "/article",
            "/article-lookup": "/article",
        }
        first_two_parts1 = "/".join(parsed_url1.path.strip("/").split("/")[:2])
        first_two_parts2 = "/".join(parsed_url2.path.strip("/").split("/")[:2])
        for old, new in replacements.items():
            first_two_parts1 = first_two_parts1.replace(old, new)
            first_two_parts2 = first_two_parts2.replace(old, new)
        if first_two_parts1 == first_two_parts2:
            print_warn(f"Possible URL Match: {url1} {url2}")
            return True
        return True

    return False


def extract_doi_from_url(url):
    """Extract DOI from URL."""
    # Common DOI patterns in URLs
    patterns = [
        r"10\.\d{4,9}/[-._;()/:A-Z0-9]+(?![.][a-z]+)",  # Basic DOI pattern
        r"doi/(?:abs/|full/|pdf/)?([^?#]+)",  # DOI in path
        r"doi:([^?#/]+/[^?#/]+)",  # DOI with prefix
    ]

    for pattern in patterns:
        matches = re.findall(pattern, url, re.IGNORECASE)
        if matches:
            # Take the first match that looks like a valid DOI
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if re.match(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", match):
                    return match

    return None


@lru_cache(maxsize=1000)
def check_doi_via_redirect(doi, expected_url, expected_html, author, attempts=1):
    if not doi:
        return False

    domain = "doi.org"
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 1 second to avoid being blocked by {domain}")
        time.sleep(1)
    last_scraped[domain] = time.time()

    short_url = f"https://doi.org/{doi}"
    headers = {"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}
    try:
        resp = requests.get(short_url, headers=headers, timeout=100, allow_redirects=True)
        resp.raise_for_status()
        follow_url = resp.url
        page_html = resp.text
        if has_captcha(page_html):
            print_warn(f"Captcha encountered on {doi} attempt {attempts}")
            if attempts > 3:
                print_misc(f"Failed to verify DOI {doi} against {expected_url}. Returning False.")
                return False
            sleep = 60 * 60 * attempts
            print_misc(f"Sleeping for {sleep} hour")
            print_error("TODO: USE TOR TO BYPASS CAPTCHA???")
            time.sleep(sleep)
            return check_doi_via_redirect(doi, expected_url, expected_html, author, attempts + 1)
        if are_urls_equal(
            follow_url, expected_url
        ):  # Check if the URL redirects to the expected URL
            return True

        if author in page_html:
            print_warn(f"Verifying DOI: '{author}' found in HTML of {doi}.")
            return True
    except requests.HTTPError as err:
        print_misc(f"HTTP error {err.response.status_code} for DOI {doi}: {err}")
    except requests.RequestException:
        pass
    return False


def has_captcha(html):
    captcha_signals = ["gs_captcha_ccl", "recaptcha", "captcha-form", "rc-doscaptcha-body"]
    return any(signal in html for signal in captcha_signals)


@lru_cache(maxsize=1000)
def get_doi_api(doi):
    if not doi:
        return None

    domain = "doi.org"
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 1 second to avoid being blocked by {domain}")
        time.sleep(1)
    last_scraped[domain] = time.time()

    api_url = f"https://doi.org/api/handles/{doi}"
    try:
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as err:
        print_error(f"HTTP error {err.response.status_code} for DOI {doi}: {err}")
        return None
    except requests.RequestException as e:
        print_error(f"Request error for DOI {doi}: {e}")
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
    """Verify DOI points to expected URL using CrossRef API."""
    try:
        api_data = get_doi_api(doi)
        if not api_data:
            return False

        resolved_url = api_data.get("URL")
        if not resolved_url:
            return False

        return are_urls_equal(resolved_url, expected_url)
    except Exception as e:
        print_warn(f"Error checking DOI via API: {str(e)}")
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

    domain = "shortdoi.org"
    if domain in last_scraped and time.time() - last_scraped[domain] < 30:
        print_misc(f"Sleeping for 1 second to avoid being blocked by {domain}")
        time.sleep(1)
    last_scraped[domain] = time.time()

    short_doi_url = f"https://shortdoi.org/{doi}?format=json"
    try:
        resp = requests.get(short_doi_url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as err:
        print_error(f"HTTP error {err.response.status_code} for short DOI {doi}: {err}")
        return None
    except requests.RequestException as e:
        print_error(f"get_doi_short_api() request error: {e}")
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
