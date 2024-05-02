import sys
import time
import json
from scholarly import scholarly
from journal_impact_factor import get_impact_factor
from doi import get_doi, get_doi_link, get_doi_short, get_doi_short_link
from standardise import standardise_authors
from logger import print_error, print_warn, print_info

if not len(sys.argv) == 2:
    print_error("Usage: python generate.py scholar_id\nExample: python generate.py ynWS968AAAAJ")
    sys.exit(1)

scholar_id = sys.argv[1]

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
        pub_url = filled_pub.get('pub_url', '')
        print(f"Publication URL: {pub_url}")
        journal_name = filled_pub.get('bib', {}).get('journal', '') if filled_pub.get('bib', {}).get('journal', '') != "Null" else ''
        print(f"Journal name: {journal_name}")

        # Standardise author names
        authors = filled_pub.get('bib', {}).get('author', '')
        standardised_authors = standardise_authors(authors)
        filled_pub['bib']['authors_standardised'] = standardised_authors

        if not "symposium" in journal_name or not "conference" in journal_name or not "workshop" in journal_name or not "annual meeting" in journal_name:
            # Get DOI
            print(f"Getting DOI for {pub_url}")
            doi = get_doi(pub_url)
            if not doi:
                print_warn("DOI not found. Trying to get DOI from the publication title.")
            else:
                print_info(f"DOI: {doi}")
            filled_pub['doi'] = doi if doi else ""

            doi_link = get_doi_link(doi)
            print(f"DOI link: {doi_link}")
            filled_pub['doi_link'] = doi_link

            doi_short = get_doi_short(doi)
            print(f"Short DOI: {doi_short}")
            filled_pub['doi_short'] = doi_short

            doi_short_link = get_doi_short_link(doi_short)
            print(f"Short DOI link: {doi_short_link}")
            filled_pub['doi_short_link'] = doi_short_link

            # Get Impact Factor
            impact_factor = None
            if journal_name:
                print(f"Getting impact factor for {journal_name}")
                impact_factor = get_impact_factor(journal_name.lower())
                print_info(f"Impact factor: {impact_factor}")
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
