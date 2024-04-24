import wikipedia
from bs4 import BeautifulSoup
import asyncio
from playwright.async_api import async_playwright
import urllib.request
from urllib.error import HTTPError
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_impact_factor(journal_name):
    impact_factor = fetch_if_from_wikipedia(journal_name+" (journal)") # E.g., https://en.wikipedia.org/wiki/Nature_(journal)
    if impact_factor is not None:
        return impact_factor
    impact_factor = fetch_if_from_wikipedia(journal_name) # E.g., https://en.wikipedia.org/wiki/Global_Change_Biology
    if impact_factor is not None:
        return impact_factor
    impact_factor = asyncio.run(fetch_if_from_bioxbio("Nature"))
    if impact_factor is not None:
        return impact_factor
    return None
    

def fetch_if_from_wikipedia(journal_name):
    journal_name = journal_name
    try:
        # Search for the page by journal name
        page = wikipedia.page(journal_name)
        
        # Access the content of the page
        html_content = page.html()
        soup = BeautifulSoup(html_content, 'html.parser')

        # Find the table row ('tr') where the 'th' (table header) contains the text 'Impact factor'
        impact_factor_row = soup.find('th', string='Impact factor')

        # Check if the row is found
        if impact_factor_row:
            # Get the next sibling 'td' which contains the impact factor
            impact_factor_data = impact_factor_row.find_next_sibling('td')
            if impact_factor_data:
                impact_factor_data_array = impact_factor_data.text.split(' ')
                impact_factor = impact_factor_data_array[0].strip()
                #year = impact_factor_data_array[1].strip().replace('(', '').replace(')', '')
                return impact_factor
            else:
                print("Impact factor not found.")
                return None
        else:
            print("Impact factor row not found.")
            return None
    except wikipedia.exceptions.PageError:
        print(f"Wikipedia page not found. {journal_name}")
        return None
    except wikipedia.exceptions.DisambiguationError as e:
        print(f"Disambiguation error, multiple entries found for '{journal_name}': {e.options}")
        # Automatically select a page if one of the options matches certain criteria
        correct_page = next((option for option in e.options if "journal" in option.lower()), None)
        if correct_page:
            page = wikipedia.page(correct_page)
        else:
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
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
                impact_factor = await page.evaluate('''() => {
                    const table = document.querySelector('table.table-bordered');
                    const secondRow = table.querySelectorAll('tr')[1];
                    return secondRow ? secondRow.children[1].textContent.trim() : 'Impact Factor not found';
                }''')

                #print(f"Impact Factor: {impact_factor}")
                return impact_factor
            else:
                print("First result link not found.")
                return None
    except Exception as e:
        print(f"Error fetching from BioxBio: {e}")
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
