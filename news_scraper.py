import requests
import json
import time
import os
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX_ID = os.getenv("GOOGLE_CX_ID")

DELAY = 1.5 # Delay between requests to avoid overwhelming servers

SCHOLAR_NAME = "Professor Dr Jodie Rummer"
RESULTS_FILE = f"{SCHOLAR_NAME.replace(' ', '_')}_portfolio.json"

def fetch_news_api(query, api_key):
    url = f"https://newsapi.org/v2/everything?q={query}&apiKey={api_key}"
    response = requests.get(url)
    response.raise_for_status()  # Check for HTTP errors
    return response.json()["articles"]

def fetch_google_search(query, api_key, cx):
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={api_key}&cx={cx}"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()["items"]

def scrape_web_content(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    articles = []
    for article in soup.find_all("div", class_="article"):
        title = article.find("h2").get_text()
        link = article.find("a")["href"]
        description = article.find("p").get_text()
        articles.append({
            "title": title,
            "link": link,
            "description": description
        })
    return articles

def main(SEARCH_TERMS):
    portfolio_data = {"news_articles": [], "interviews": [], "podcasts": []}
    
    # Fetch articles from NewsAPI
    print("Fetching news articles...")
    news_articles = fetch_news_api(SEARCH_TERMS, NEWS_API_KEY)
    portfolio_data["news_articles"].extend(news_articles)
    time.sleep(DELAY)

    # Fetch data from Google Custom Search API
    print("Fetching Google search results...")
    try:
        google_results = fetch_google_search(SEARCH_TERMS, GOOGLE_API_KEY, GOOGLE_CX_ID)
        portfolio_data["interviews"].extend(google_results)
    except requests.HTTPError as e:
        print(f"Failed to fetch Google results: {e}")
    time.sleep(DELAY)

    # Example scrape (customised for specific site structure)
    print("Scraping additional sources...")
    additional_articles = scrape_web_content(SEARCH_TERMS)
    portfolio_data["news_articles"].extend(additional_articles)
    time.sleep(DELAY)

    # Save results to a JSON file
    with open(RESULTS_FILE, "w") as file:
        json.dump(portfolio_data, file, indent=4)

    print("Data collection complete. Results saved to", RESULTS_FILE)

if __name__ == "__main__":
    main(SCHOLAR_NAME)
