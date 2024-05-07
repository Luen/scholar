from mediawiki import MediaWiki, DisambiguationError
import time
from bs4 import BeautifulSoup
import asyncio
from playwright.async_api import async_playwright
import urllib.request
from urllib.error import HTTPError
from functools import lru_cache
from logger import print_error, print_warn, print_info


# Create a MediaWiki object to interface with Wikipedia
wikipedia = MediaWiki()


@lru_cache(maxsize=1000)
def get_impact_factor(journal_name):
    if not journal_name:
        return None
    impact_factor = fetch_if_from_wikipedia(journal_name) 
    if impact_factor is not None:
        return impact_factor
    impact_factor = fetch_if_from_wikipedia(journal_name) 
    if impact_factor is not None:
        return impact_factor
    impact_factor = asyncio.run(fetch_if_from_bioxbio(journal_name))
    if impact_factor is not None:
        return impact_factor
    return None

@lru_cache(maxsize=1000)
def fetch_if_from_wikipedia(journal_name):
    try:
        # Try to get the Wikipedia page for the journal
        page = wikipedia.page(journal_name.replace(' ', '_').title()+"_(journal)") # E.g., https://en.wikipedia.org/wiki/Significance_(journal)
        if page:
            impact_factor = parse_if_from_wikipedia(page.html())
            if impact_factor is False:
                return None
            if impact_factor is not None:
                return impact_factor 

        time.sleep(10)
        page = None
        # Try searching for the journal name
        search = wikipedia.search(journal_name+" (journal)") # E.g., https://en.wikipedia.org/wiki/Nature_(journal)
        if search is not None or len(search) != 0:
            option = search[0]
            if "(journal)" in option:
                time.sleep(10)
                page = wikipedia.page(option)
            if page:
                impact_factor = parse_if_from_wikipedia(page.html())
                if impact_factor is False:
                    return None
                if impact_factor is not None:
                    return impact_factor
        
        page = None
        time.sleep(10)
        search = wikipedia.search(journal_name) # E.g., https://en.wikipedia.org/wiki/Global_Change_Biology
        if search is not None or len(search) != 0:
            time.sleep(10)
            page = wikipedia.page(search[0])
            if page:
                impact_factor = parse_if_from_wikipedia(page.html())
                if impact_factor is False:
                    return None
                if impact_factor is not None:
                    return impact_factor
        
        print_warn(f"Impact Factor not found on Wikipedia page {journal_name}")
        return None
    except Exception as e:
        print_error(f"An error occurred: {e}")
        return None

def parse_if_from_wikipedia(html_content):
    if not html_content:
        return None
    soup = BeautifulSoup(html_content, "html.parser")
    impact_factor_row = soup.find('th', string='Impact factor')
    if impact_factor_row:
        impact_factor_data = impact_factor_row.find_next_sibling('td')
        if impact_factor_data:
            impact_factor_data_array = impact_factor_data.text.strip().split(' ')
            impact_factor = impact_factor_data_array[0].strip()
            year = impact_factor_data_array[1].strip().replace('(', '').replace(')', '')
            current_year = int(time.strftime("%Y"))
            if year and int(year) <= (current_year - 2):
                print_warn(f"Year is {year}. Impact Factor outdated.")
                return False
            return impact_factor
    return None


# Fetch impact factor from somewhere else
async def fetch_if_from_bioxbio(journal_name):
    #https://www.bioxbio.com/journal/NATURE
    #https://www.bioxbio.com/journal/PLOS-ONE
    #https://www.bioxbio.com/journal/T-AM-FISH-SOC
    #https://www.bioxbio.com/journal/COMP-BIOCHEM-PHYS-A
    try:
        print(f"Fetching impact factor from BioxBio for {journal_name}")
        async with async_playwright() as p:
            # Launch the browser
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Construct the URL and navigate to the page
            url = f"https://www.bioxbio.com/search/?q={journal_name.replace(' ', '+')}"
            await page.goto(url)

            # Wait for the necessary elements to load
            await page.wait_for_selector('div.gsc-expansionArea', timeout=10000)

            # Get the search results
            results = await page.query_selector_all('div.gsc-webResult.gsc-result')
            if not results:
                print("No results found")
                return None

            first_result_link = await results[0].query_selector('a.gs-title')
            if first_result_link:
                # Click the first result link and wait for the navigation to complete
                link = await first_result_link.get_attribute('href')
                await page.goto(link, wait_until='load')

                # Wait for the table to load on the new page
                #await page.wait_for_selector('table.table-bordered', timeout=10000)

                # Directly extract the Impact Factor from the table using Playwright
                impact_factor_array = await page.evaluate('''() => {
                    const table = document.querySelector('table.table-bordered');
                    if (!table) {
                        return [];
                    }
                    const secondRow = table.querySelectorAll('tr')[1];
                    return secondRow ? [
                        secondRow.children[0].textContent.trim(),
                        secondRow.children[1].textContent.trim()
                    ] : [];
                }''')

                if not impact_factor_array or len(impact_factor_array) != 2:
                    print_warn("Impact Factor table not found.")
                    return None

                # Extracting year and impact factor
                year = impact_factor_array[0].split(' ')[0] if impact_factor_array else None
                impact_factor = impact_factor_array[1] if impact_factor_array else None
                if not impact_factor:
                    print_warn("Impact Factor not found.")
                    return None
                
                current_year = int(time.strftime("%Y"))
                if year and int(year) <= (current_year - 2):
                    print_warn(f"Year is {year}. Impact Factor outdated.")
                    return None

                #print(f"Impact Factor: {impact_factor}")
                return impact_factor
            
            print_warn("First result link not found.")
        return None
    except Exception as e:
        print_error(f"Error fetching from BioxBio: {e}")
        return None
    finally:
        await browser.close()


def fetch_if_from_journalguide(journal_name):
    #https://www.journalguide.com/journals/nature
    return None

#def fetch_if_from_scimago(journal_name):

#def fetch_if_from_sjr(journal_name):

#def fetch_if_from_jcr(journal_name):

#def fetch_if_from_scopus(journal_name):

#def fetch_if_from_web_of_science(journal_name):

#def fetch_if_from_pubmed(journal_name):

#def fetch_if_from_crossref(journal_name):

