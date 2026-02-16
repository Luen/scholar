# Generate a JSON file with the author's publications, including DOI and Impact Factor
# Configure HTTP cache before any requests (scholarly, DOI APIs, Hero scraper, etc.)
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import urlparse

from scholarly import scholarly

import src.cache_config  # noqa: F401


def _log_step(step: str, detail: str = ""):
    """Log current step with timestamp for progress visibility."""
    ts = datetime.now().strftime("%H:%M:%S")
    msg = f"[{ts}] {step}" + (f" — {detail}" if detail else "")
    print(msg, flush=True)
    log_to_file("STEP", msg)
from src.doi import (
    are_urls_equal,
    get_doi,
    get_doi_from_title,
    get_doi_link,
    get_doi_resolved_link,
    get_doi_short,
    get_doi_short_link,
)
from src.journal_impact_factor import add_impact_factor, load_impact_factor
from src.logger import log_to_file, print_error, print_info, print_misc, print_warn
from src.news_scraper import get_news_data
from src.video_scraper import get_video_data
from src.standardise import standardise_authors

if not len(sys.argv) == 2:
    print_error("Usage: python main.py scholar_id\nExample: python main.py ynWS968AAAAJ")
    sys.exit(1)

scholar_id = sys.argv[1]

journal_impact_factor_dic = load_impact_factor()
print_info(f"Loaded {len(journal_impact_factor_dic)} impact factors from Google Sheet.")

if not os.path.exists("scholar_data"):
    os.makedirs("scholar_data")
file_path = os.path.join("scholar_data", f"{scholar_id}.json")

# Load previous data, if available
previous_data = {}
if os.path.exists(file_path):
    with open(file_path) as f:
        previous_data = json.load(f)
        print_info(f"Loaded previous data for {scholar_id}.")

try:
    _log_step("START", f"scholar_id={scholar_id}")
    print_misc(
        "This script will take a while due to rate limits. Google Scholar may show CAPTCHA; "
        "in Docker/headless mode this can block indefinitely."
    )
    _log_step("Fetching author profile", "calling scholarly.search_author_id (may wait for CAPTCHA if detected)")
    author = scholarly.search_author_id(scholar_id)
    if not author:
        print_error("Author not found")
        sys.exit(1)
    _log_step("Author profile received", author.get("name", "Unknown"))

    _log_step("Filling author details", "publications, citations, etc.")
    author = scholarly.fill(author)
    _log_step("Author details filled", f"{len(author.get('publications', []))} publications")

    # Fill coauthors data
    coauthor_count = len(author.get("coauthors", []))
    _log_step("Fetching coauthors", f"{coauthor_count} coauthors")
    if "coauthors" in author:
        filled_coauthors = []
        for i, coauthor in enumerate(author["coauthors"]):
            try:
                _log_step("Coauthor", f"{i + 1}/{coauthor_count}: {coauthor.get('name', 'Unknown')}")
                filled_coauthor = scholarly.fill(coauthor)
                filled_coauthors.append(filled_coauthor)
                time.sleep(2)  # Be nice to Google Scholar
            except Exception as e:
                print_warn(
                    f"Error fetching data for coauthor {coauthor.get('name', 'Unknown')}: {str(e)}"
                )
                filled_coauthors.append(coauthor)  # Add unfilled data if there's an error
        author["coauthors"] = filled_coauthors

    filled_publications = []
    total_pubs = len(author["publications"])
    _log_step("Processing publications", f"{total_pubs} total")

    # Process each publication
    for index, pub in enumerate(author["publications"]):
        pub_title = pub.get("bib", {}).get("title", "?")[:60]
        _log_step("Publication", f"{index + 1}/{total_pubs}: {pub_title}")

        # If already in json file, get data from there but use new Impact Factor.
        if (
            previous_data.get("publications", [])
            and len(previous_data.get("publications", [])) > index
        ):
            filled_pub = previous_data.get("publications", [])[index]
            _log_step("Using cached", "existing data, updating Impact Factor")
            journal_name = (
                filled_pub.get("bib", {}).get("journal", "")
                if filled_pub.get("bib", {}).get("journal", "") != "Null"
                else ""
            )
            journal_name = journal_name.strip().lower()
            if journal_name in journal_impact_factor_dic:
                filled_pub["bib"]["impact_factor"] = journal_impact_factor_dic[journal_name]
            filled_publications.append(filled_pub)
            continue

        _log_step("Filling publication", "fetching from Google Scholar")
        filled_pub = scholarly.fill(pub)
        pub_title = filled_pub.get("bib", {}).get("title", "")
        pub_url = filled_pub.get("pub_url", "")
        journal_name = (
            filled_pub.get("bib", {}).get("journal", "")
            if filled_pub.get("bib", {}).get("journal", "") != "Null"
            else ""
        )
        print_misc(f"Journal name: {journal_name}")

        # Standardise author names
        authors = filled_pub.get("bib", {}).get("author", "")
        standardised_authors = standardise_authors(authors)
        filled_pub["bib"]["authors_standardised"] = standardised_authors

        if (
            "symposium" in journal_name
            or "conference" in journal_name
            or "workshop" in journal_name
            or "annual meeting" in journal_name
        ):
            print_warn(
                f"Skipping DOI and Impact Factor for symposium, conference, workshop, or annual meeting: {journal_name}"
            )
            filled_pub["doi"] = ""
            filled_pub["doi_link"] = ""
            filled_pub["doi_short"] = ""
            filled_pub["doi_short_link"] = ""
            filled_pub["bib"]["impact_factor"] = ""
        else:
            # Get DOI
            _log_step("Getting DOI", pub_url[:80] + "..." if len(pub_url) > 80 else pub_url)

            # Get DOI from previous data, if available
            doi = (
                previous_data.get("publications", [])[index].get("doi", "")
                if previous_data.get("publications", [])
                else None
            )

            # Initialize variables
            doi_link = None
            doi_short = None
            doi_short_link = None
            resolved_link = None

            # e.g., https://scholar.google.com/scholar?cluster=4186906934658759747&hl=en&oi=scholarr
            if not doi:
                host = urlparse(pub_url).hostname
                if host and host == "scholar.google.com" and pub_title:
                    doi = get_doi_from_title(pub_title, author["name"].split()[-1])
                else:
                    doi = get_doi(pub_url, author["name"].split()[-1])
            if not doi:
                print_warn("DOI not found. Trying to get DOI from the publication title.")
            else:
                print_info(f"DOI: {doi}")

                # Get doi_link from previous data, if available
                doi_link = (
                    previous_data.get("publications", [])[index].get("doi_link", "")
                    if previous_data.get("publications", [])
                    else None
                )
                if not doi_link:
                    doi_link = get_doi_link(doi)
                    print_misc(f"DOI link: {doi_link}")
                    resolved_link = get_doi_resolved_link(doi)
                    print_misc(f"DOI Resolves to: {resolved_link}")
                    if not are_urls_equal(pub_url, resolved_link):
                        print_warn(
                            f"Resolved link does not match publication URL:\n{pub_url}\n{resolved_link}"
                        )

                # Get doi_short from previous data, if available
                doi_short = (
                    previous_data.get("publications", [])[index].get("doi_short", "")
                    if previous_data.get("publications", [])
                    else None
                )
                if not doi_short:
                    doi_short = get_doi_short(doi)
                    print_misc(f"Short DOI: {doi_short}")

                # Get doi_short_link from previous data, if available
                doi_short_link = (
                    previous_data.get("publications", [])[index].get("doi_short_link", "")
                    if previous_data.get("publications", [])
                    else None
                )
                if not doi_short_link:
                    doi_short_link = get_doi_short_link(doi_short)

            # Add DOI and Impact Factor to publication
            filled_pub["doi"] = doi if doi else ""
            filled_pub["doi_short_link"] = doi_short_link if doi_short_link else ""
            filled_pub["doi_short"] = doi_short if doi_short else ""
            filled_pub["doi_link"] = doi_link if doi_link else ""
            filled_pub["doi_resolved_link"] = resolved_link if resolved_link else ""

            # Get Impact Factor
            missing_journals = set()
            impact_factor = None
            if journal_name:
                journal_name = (
                    journal_name.strip().lower()
                )  # Ensure journal name is lowercase for lookup
                if journal_name in journal_impact_factor_dic:
                    impact_factor = journal_impact_factor_dic[journal_name]
                else:
                    if journal_name not in missing_journals:
                        print_warn(
                            "TODO: Implement a search function if the journal name isn't exactly the same - e.g., levenshtein. OR FILL OUT IMPACT FACTOR SHEET."
                        )
                        print_error(
                            f"Missing impact factor for {journal_name}. Adding to Google Sheet so you can add."
                        )
                        missing_journals.add(journal_name)
                        add_impact_factor(journal_name, "")
            else:
                print_warn("Journal name not found.")
            filled_pub["bib"]["impact_factor"] = impact_factor

        # Add to list of processed publications
        filled_publications.append(filled_pub)

        with open(file_path, "w") as f:
            json.dump(author, f, indent=4)

        _log_step("Sleeping", "1s (rate limit)")
        time.sleep(1)

    # Update the author data with processed publications
    author["publications"] = filled_publications

    # Get news and RSS data
    _log_step("Fetching news/RSS", author["name"])
    rss_data = get_news_data(author["name"])
    author.update(rss_data)

    # Get video data (mock for now)
    _log_step("Fetching video data")
    video_data = get_video_data(author["name"])
    author.update(video_data)

    # Write author to file in JSON format
    _log_step("Writing output", file_path)
    with open(file_path, "w") as f:
        json.dump(author, f, indent=4)
    _log_step("DONE", file_path)
    print_info(f"Author data written to {file_path}")

except AttributeError as e:
    print_error(f"AttributeError: {e}")
    sys.exit(1)
except Exception as e:
    print_error(f"An error occurred: {e}")
    sys.exit(1)
