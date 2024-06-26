# Generate a JSON file with the author's publications, including DOI and Impact Factor

import sys
import time
import json
from scholarly import scholarly
from journal_impact_factor import get_impact_factor
from doi import get_doi, get_doi_from_title, get_doi_link, get_doi_resolved_link, get_doi_short, get_doi_short_link, are_urls_equal
from standardise import standardise_authors
from logger import print_error, print_warn, print_info

if not len(sys.argv) == 2:
    print_error("Usage: python generate.py scholar_id\nExample: python generate.py ynWS968AAAAJ")
    sys.exit(1)

scholar_id = sys.argv[1]


def load_impact_factor_json_file(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print_warn(f"Error loading JSON from {file_path}. File may be empty or malformed.")
        return {}
    except FileNotFoundError:
        print_warn(f"File {file_path} not found. Creating a new one.")
        return {}
    
def save_impact_factor_json_file(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)


try:
    print(f"Getting author with ID: {scholar_id}")
    print("This script will take a while to complete due to the rate limits of the scraping website and APIs used")
    author = scholarly.search_author_id(scholar_id)
    if not author or author is None:
        print_error("Author not found")
        sys.exit(1)  # Exit if no author found

    author = scholarly.fill(author)
    filled_publications = []

    # Process each publication
    for index, pub in enumerate(author["publications"]):
        #publication number of the publications
        print(f"Processing publication {index+1}/{len(author['publications'])}: {pub['bib']['title']}")

        filled_pub = scholarly.fill(pub)
        pub_title = filled_pub.get('bib', {}).get('title', '')
        pub_url = filled_pub.get('pub_url', '')
        journal_name = filled_pub.get('bib', {}).get('journal', '') if filled_pub.get('bib', {}).get('journal', '') != "Null" else ''
        print(f"Journal name: {journal_name}")

        # Standardise author names
        authors = filled_pub.get('bib', {}).get('author', '')
        standardised_authors = standardise_authors(authors)
        filled_pub['bib']['authors_standardised'] = standardised_authors

        if not ("symposium" in journal_name or "conference" in journal_name or "workshop" in journal_name or "annual meeting" in journal_name):
            # Get DOI
            print(f"Getting DOI for {pub_url}")

            # e.g., https://scholar.google.com/scholar?cluster=4186906934658759747&hl=en&oi=scholarr
            #host = urlparse(url).hostname
            #if host and host.endswith("scholar.google.com"):
            if "scholar.google.com" in pub_url and pub_title:
                doi = get_doi_from_title(pub_title)
            else: 
                doi = get_doi(pub_url)
            if not doi:
                print_warn("DOI not found. Trying to get DOI from the publication title.")
            else:
                print_info(f"DOI: {doi}")
                doi_link = get_doi_link(doi)
                print(f"DOI link: {doi_link}")
                resolved_link = get_doi_resolved_link(doi)
                print(f"DOI Resolves to: {resolved_link}")
                if not are_urls_equal(pub_url, resolved_link):
                    print_warn(f"Resolved link does not match publication URL:\n{pub_url}\n{resolved_link}")
                doi_short = get_doi_short(doi)
                print(f"Short DOI: {doi_short}")
                doi_short_link = get_doi_short_link(doi_short)

            # Add DOI and Impact Factor to publication
            filled_pub['doi'] = doi if doi else ""
            filled_pub['doi_short_link'] = doi_short_link if doi_short_link else ""
            filled_pub['doi_short'] = doi_short if doi_short else ""
            filled_pub['doi_link'] = doi_link if doi_link else ""
            filled_pub['doi_resolved_link'] = resolved_link if resolved_link else ""

            # Get Impact Factor
            impact_factor_json = load_impact_factor_json_file("journal_impact_factor.json")
            impact_factor = None
            if journal_name:
                if journal_name.lower() not in impact_factor_json:
                    print_warn("TODO: Implement a search function if the journal name isn't exactly the same - e.g., levenshtein.") # https://github.com/Luen/google-scholar-references-py/blob/main/references.py
                    print(f"Getting impact factor for {journal_name}")
                    impact_factor = get_impact_factor(journal_name.lower())
                    print_info(f"Impact factor: {impact_factor}")
                    # Add impact factor to journal_impact_factor.json
                    impact_factor_json[journal_name.lower()] = impact_factor
                    save_impact_factor_json_file("journal_impact_factor.json", impact_factor_json)
                else:
                    print_info(f"Impact factor found in journal_impact_factor.json")
            else:
                print_warn(f"Journal name not found.")
            filled_pub['bib']['impact_factor'] = impact_factor

        else: 
            print_warn(f"Skipping DOI and Impact Factor for symposium, conference, workshop, or annual meeting: {journal_name}")
            filled_pub['doi'] = ""
            filled_pub['doi_link'] = ""
            filled_pub['doi_short'] = ""
            filled_pub['doi_short_link'] = ""
            filled_pub['bib']['impact_factor'] = ""

        # Add to list of processed publications
        filled_publications.append(filled_pub)
        print("Sleeping for 10 seconds...")
        time.sleep(10)  # Be polite with the rate of requests

    # Update the author data with processed publications
    author["publications"] = filled_publications
    
    # Write author to file in JSON format
    with open(f"{scholar_id}.json", "w") as f:
        json.dump(author, f, indent=4)
    print_info(f"DONE. Author data written to {scholar_id}.json")

except AttributeError as e:
    print_error(f"AttributeError: {e}")

except Exception as e:
    print_error(f"An error occurred: {e}")
