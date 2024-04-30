import sys
import time
import json
from scholarly import scholarly
from journal_impact_factor import get_impact_factor
from doi import get_doi
from standardise import standardise_authors

if not len(sys.argv) == 2:
    print("Usage: python generate.py scholar_id\nExample: python generate.py ynWS968AAAAJ")
    sys.exit(1)

scholar_id = sys.argv[1]

try:
    print(f"Getting author with ID: {scholar_id}")
    author = scholarly.search_author_id(scholar_id)
    if not author or author is None:
        print("Author not found")
        sys.exit(1)  # Exit if no author found

    author = scholarly.fill(author)
    filled_publications = []

    # Process each publication
    for pub in author["publications"]:
        print(f"Processing publication: {pub['bib']['title']}")

        filled_pub = scholarly.fill(pub)
        pub_url = filled_pub.get('pub_url', '')
        journal_name = filled_pub.get('bib', {}).get('journal', '')

        # Standardise author names
        authors = filled_pub.get('bib', {}).get('author', '')
        standardised_authors = standardise_authors(authors)
        filled_pub['authors_standardised'] = standardised_authors

        if not "symposium" in journal_name or not "conference" in journal_name or not "workshop" in journal_name or not "annual meeting" in journal_name:
            # Get DOI
            print(f"Getting DOI for {pub_url}")
            doi = get_doi(pub_url)
            print(f"DOI: {doi}")
            filled_pub['doi'] = doi if doi else ""

            # Get Impact Factor
            impact_factor = None
            if journal_name and journal_name != "Null":
                print(f"Getting impact factor for {journal_name}")
                impact_factor = get_impact_factor(journal_name.lower())
                print(f"Impact factor: {impact_factor}")
            else:
                print(f"Journal name not found: {journal_name}")
            filled_pub['impact_factor'] = impact_factor
        else: 
            print(f"Skipping DOI and Impact Factor for symposium, conference, workshop, or annual meeting: {journal_name}")
            filled_pub['doi'] = ""
            filled_pub['impact_factor'] = ""

        # Add to list of processed publications
        filled_publications.append(filled_pub)
        time.sleep(10)  # Be polite with the rate of requests

    # Update the author data with processed publications
    author["publications"] = filled_publications
    
    # Write author to file in JSON format
    with open(f"{scholar_id}.json", "w") as f:
        json.dump(author, f, indent=4)

except AttributeError as e:
    print(f"AttributeError: {e}")

except Exception as e:
    print(f"An error occurred: {e}")
