import feedparser
import json
import re
import os
import time
from datetime import datetime
from typing import List, Dict, Optional, TypedDict, Literal
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from email.utils import parsedate_to_datetime
import pytz

load_dotenv()

# Keywords: "Rummer", "Rummerlab", and "Physioshark"

# Constants
REVALIDATE_TIME = 604800  # One week in seconds
SCHOLAR_NAME = "Professor Dr Jodie Rummer"

DEFAULT_HEADERS = {
    'Accept': 'application/atom+xml,application/xml,text/xml,application/rss+xml',
    'User-Agent': 'Mozilla/5.0 (compatible; RummerLab/1.0; +https://rummerlab.org)'
}

MODERN_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.townsvillebulletin.com.au',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1'
}

class MediaItem(TypedDict):
    type: Literal['article']
    source: str
    title: str
    description: str
    url: str
    date: str
    sourceType: str
    image: Optional[Dict[str, str]]

def strip_html(html: str) -> str:
    """Remove HTML tags and entities from text."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html)
    # Remove HTML entities
    text = re.sub(r'&[^;]+;', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove "Exclusive:" or "Live:" prefix
    text = re.sub(r'^(Exclusive|Live):\s*', '', text, flags=re.IGNORECASE)
    return text.strip()

def extract_image_from_content(content: str) -> Optional[str]:
    """Extract image URL from HTML content."""
    match = re.search(r'<img[^>]+src="([^">]+)"', content or '')
    return match.group(1) if match else None

def does_article_mention_rummer(content: str, title: str, description: str) -> bool:
    """Check if article mentions Rummer in a meaningful way."""
    normalized_content = content.lower()
    normalized_title = title.lower()
    normalized_description = description.lower()
    
    return (
        'rummer' in normalized_title or 
        'rummer' in normalized_description or 
        ('rummer' in normalized_content and 
         (normalized_content.count('rummer') > 1 or
          any(term in normalized_content for term in ['dr rummer', 'dr. rummer', 'professor rummer', 'jodie rummer'])))
    )

def contains_marine_keywords(content: str, title: str, description: str) -> bool:
    """Check if content contains marine-related keywords."""
    text = f"{content} {title} {description}".lower()
    keywords = ['marine', 'reef', 'shark', 'fish', 'ocean']
    return any(keyword in text for keyword in keywords)

def standardize_date(date_str: Optional[str]) -> str:
    """
    Convert various date formats to ISO 8601 format (YYYY-MM-DDThh:mm:ssZ).
    Falls back to current UTC time if date can't be parsed.
    """
    if not date_str:
        return datetime.now(pytz.UTC).isoformat().replace('+00:00', 'Z')
    
    try:
        # Try parsing as RFC 2822 (common in RSS feeds)
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone(pytz.UTC).isoformat().replace('+00:00', 'Z')
        except:
            pass
        
        # Try parsing as ISO format
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.astimezone(pytz.UTC).isoformat().replace('+00:00', 'Z')
        except:
            pass
        
        # Try common formats
        for fmt in [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y',
        ]:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.UTC)
                return dt.astimezone(pytz.UTC).isoformat().replace('+00:00', 'Z')
            except:
                continue
                
        # If all parsing attempts fail, use current time
        return datetime.now(pytz.UTC).isoformat().replace('+00:00', 'Z')
    except Exception as e:
        print(f"Error standardizing date {date_str}: {e}")
        return datetime.now(pytz.UTC).isoformat().replace('+00:00', 'Z')


def fetch_google_search(query):
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_CX_ID = os.getenv("GOOGLE_CX_ID")
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={GOOGLE_CX_ID}"
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

def get_news_data(scholar_name):
    """Function to fetch all news data for a scholar that can be used by main.py"""
    news_data = {"news_articles": [], "interviews": [], "podcasts": []}

    google_results = fetch_google_search(scholar_name)
    news_data["interviews"].extend(google_results)
    
    additional_articles = scrape_web_content(scholar_name)
    news_data["news_articles"].extend(additional_articles)

    return news_data


def fetch_rss_feed(url: str, source: str, filter_fn=None, headers=DEFAULT_HEADERS) -> List[MediaItem]:
    """Fetch and parse an RSS feed."""
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        feed = feedparser.parse(response.text)
        
        articles = []
        for item in feed.entries:
            if filter_fn and not filter_fn(item):
                continue
                
            content = getattr(item, 'content', [{}])[0].get('value', '') if hasattr(item, 'content') else ''
            description = getattr(item, 'description', '') or getattr(item, 'summary', '')
            
            # Get the most accurate date available
            date_str = item.get('published', '') or item.get('updated', '') or item.get('created', '')
            
            media_item: MediaItem = {
                'type': 'article',
                'source': source,
                'title': strip_html(item.title),
                'description': strip_html(description),
                'url': item.link,
                'date': standardize_date(date_str),
                'sourceType': source if source in ['The Guardian', 'The Conversation', 'ABC News', 'CNN'] else 'Other'
            }
            
            # Add image if available
            if hasattr(item, 'enclosures') and item.enclosures:
                enclosure = item.enclosures[0]
                if 'url' in enclosure:
                    media_item['image'] = {
                        'url': enclosure.url,
                        'alt': strip_html(item.title)
                    }
            elif content:
                image_url = extract_image_from_content(content)
                if image_url:
                    media_item['image'] = {
                        'url': image_url,
                        'alt': strip_html(item.title)
                    }
                    
            articles.append(media_item)
            
        return articles
    except Exception as e:
        print(f"Error fetching {source} RSS feed: {str(e)}")
        return []

def fetch_conversation_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://theconversation.com/profiles/jodie-l-rummer-711270/articles.atom',
        'The Conversation',
        lambda _: True
    )

def fetch_abc_news_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://www.abc.net.au/news/feed/51120/rss.xml',
        'ABC News',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_science_daily_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://www.sciencedaily.com/rss/plants_animals/marine_biology.xml',
        'Science Daily',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_guardian_articles() -> List[MediaItem]:
    api_key = os.getenv('THE_GUARDIAN_API_KEY')
    if not api_key:
        print("Guardian API key not found in environment variables")
        return []
        
    try:
        url = f"https://content.guardianapis.com/search"
        params = {
            'q': '"Rummer"',
            'show-fields': 'headline,trailText,thumbnail,bodyText',
            'api-key': api_key
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        articles = []
        for article in data['response']['results']:
            if not does_article_mention_rummer(
                article['fields'].get('bodyText', ''),
                article['fields'].get('headline', ''),
                article['fields'].get('trailText', '')
            ):
                continue
                
            # Skip blog posts and live updates
            if any(term in article['fields'].get('headline', '').lower() for term in 
                  ['live updates', 'as it happened', 'live blog', 'live coverage',
                   'live report', 'live reaction', 'live news', 'crossword']):
                continue
                
            media_item: MediaItem = {
                'type': 'article',
                'source': 'The Guardian',
                'title': strip_html(article['fields']['headline']),
                'description': strip_html(article['fields'].get('trailText', '')),
                'url': article['webUrl'],
                'date': article['webPublicationDate'],
                'sourceType': 'The Guardian'
            }
            
            if article['fields'].get('thumbnail'):
                media_item['image'] = {
                    'url': article['fields']['thumbnail'],
                    'alt': strip_html(article['fields']['headline'])
                }
                
            articles.append(media_item)
            
        return articles
    except Exception as e:
        print(f"Error fetching Guardian articles: {str(e)}")
        return []

def fetch_townsville_bulletin_articles() -> List[MediaItem]:
    try:
        response = requests.get(
            'https://www.townsvillebulletin.com.au/news/townsville',
            headers=MODERN_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []
        
        for article in soup.find_all('article'):
            title_elem = article.find(['h2', 'h3', 'h4'])
            link_elem = article.find('a')
            date_elem = article.find(attrs={'datetime': True})
            desc_elem = article.find('p')
            
            if not (title_elem and link_elem):
                continue
                
            title = strip_html(title_elem.text)
            url = urljoin('https://www.townsvillebulletin.com.au', link_elem['href'])
            date = standardize_date(date_elem['datetime'] if date_elem else None)
            description = strip_html(desc_elem.text) if desc_elem else ''
            
            content = f"{title} {description}".lower()
            if not does_article_mention_rummer(content, title, description):
                continue
                
            media_item: MediaItem = {
                'type': 'article',
                'source': 'Townsville Bulletin',
                'title': title,
                'description': description,
                'url': url,
                'date': date,
                'sourceType': 'Other'
            }
            
            articles.append(media_item)
            
        return articles
    except Exception as e:
        print(f"Error fetching Townsville Bulletin articles: {str(e)}")
        return []

def fetch_yahoo_news_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://au.news.yahoo.com/rss',
        'Yahoo News AU',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_newscomau_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://www.news.com.au/content-feeds/latest-news-national/',
        'news.com.au',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_abc_science_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://www.abc.net.au/science/news/topic/enviro/enviro.xml',
        'ABC Science',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_newscomau_science_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'http://feeds.news.com.au/public/rss/2.0/news_tech_506.xml',
        'News.com.au Science',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_smh_science_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'http://www.smh.com.au/rssheadlines/health/article/rss.xml',
        'Sydney Morning Herald',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_sbs_science_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://www.sbs.com.au/news/feed',
        'SBS News',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fetch_cairns_news_articles() -> List[MediaItem]:
    return fetch_rss_feed(
        'https://cairnsnews.org/feed/',
        'Cairns News',
        lambda item: does_article_mention_rummer(
            getattr(item, 'content', [{}])[0].get('value', ''),
            item.title,
            getattr(item, 'description', '')
        )
    )

def fix_google_news_url(url: str) -> str:
    """Fix Google News URLs to get the actual article URL."""
    if not url:
        return ''
    
    try:
        # Handle Google News redirect URLs
        if 'news.google.com/rss/articles/' in url:
            # Extract the actual URL from the Google News redirect
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            if 'url' in query_params:
                try:
                    return query_params['url'][0]
                except:
                    return url.replace('/rss/articles/', '/articles/')
            return url.replace('/rss/articles/', '/articles/')
        
        # Handle relative URLs from Google News
        if url.startswith('./'):
            return f"https://news.google.com/{url[2:]}"
        if not url.startswith('http'):
            return f"https://news.google.com/{url}"
        
        return url
    except Exception as e:
        print(f'Error processing Google News URL: {e}')
        return url

def fetch_google_news_articles() -> List[MediaItem]:
    try:
        response = requests.get(
            'https://news.google.com/rss/search?q=Jodie+Rummer+OR+Great+Barrier+Reef+OR+James+Cook+University&hl=en-AU&gl=AU&ceid=AU:en',
            headers=DEFAULT_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        
        feed = feedparser.parse(response.text)
        articles = []
        
        for item in feed.entries:
            content = getattr(item, 'content', [{}])[0].get('value', '') if hasattr(item, 'content') else ''
            description = getattr(item, 'description', '') or getattr(item, 'summary', '')
            
            if not does_article_mention_rummer(content, item.title, description):
                continue
            
            # Get URL from description if available, as it contains the direct link
            desc_url = None
            if description:
                url_match = re.search(r'href="([^"]+)"', description)
                if url_match:
                    desc_url = url_match.group(1)
            
            url = fix_google_news_url(desc_url or item.link or item.get('guid'))
            
            # Get the most accurate date available
            date_str = item.get('published', '') or item.get('updated', '') or item.get('created', '')
            
            media_item: MediaItem = {
                'type': 'article',
                'source': 'Google News',
                'title': strip_html(item.title),
                'description': strip_html(description),
                'url': url,
                'date': standardize_date(date_str),
                'sourceType': 'Other'
            }
            
            if hasattr(item, 'enclosures') and item.enclosures:
                enclosure = item.enclosures[0]
                if 'url' in enclosure:
                    media_item['image'] = {
                        'url': enclosure.url,
                        'alt': strip_html(item.title)
                    }
            
            articles.append(media_item)
        
        return articles
    except Exception as e:
        print(f'Error fetching Google News articles: {e}')
        return []

def fetch_newsapi_articles() -> List[MediaItem]:
    api_key = os.getenv('NEWS_API_ORG_KEY')
    if not api_key:
        print('NEWS_API_ORG_KEY is not defined in environment variables')
        return []
    
    try:
        url = 'https://newsapi.org/v2/everything'
        params = {
            'q': '"Rummer"',
            'language': 'en',
            'sortBy': 'publishedAt',
            'apiKey': api_key
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('articles'):
            return []
        
        articles = []
        for article in data['articles']:
            media_item: MediaItem = {
                'type': 'article',
                'source': article['source']['name'],
                'title': article['title'],
                'description': article['description'],
                'url': article['url'],
                'date': standardize_date(article['publishedAt']),
                'sourceType': 'Other'
            }
            
            if article.get('urlToImage'):
                media_item['image'] = {
                    'url': article['urlToImage'],
                    'alt': article['title']
                }
            
            articles.append(media_item)
        
        return articles
    except Exception as e:
        print(f'Error fetching NewsAPI articles: {e}')
        return []

def fetch_all_news() -> List[MediaItem]:
    """Fetch news from all sources and combine them."""
    fetch_functions = [
        fetch_conversation_articles,
        fetch_abc_news_articles,
        fetch_science_daily_articles,
        fetch_guardian_articles,
        fetch_townsville_bulletin_articles,
        fetch_yahoo_news_articles,
        fetch_newscomau_articles,
        fetch_abc_science_articles,
        fetch_newscomau_science_articles,
        fetch_smh_science_articles,
        fetch_sbs_science_articles,
        fetch_cairns_news_articles,
        fetch_google_news_articles,
        fetch_newsapi_articles
    ]
    
    all_articles = []
    for fetch_fn in fetch_functions:
        try:
            articles = fetch_fn()
            all_articles.extend(articles)
            time.sleep(1)  # Be nice to the servers
        except Exception as e:
            print(f"Error in {fetch_fn.__name__}: {str(e)}")
            
    # Remove duplicates based on URL and sort by date
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        if article['url'] not in seen_urls:
            seen_urls.add(article['url'])
            unique_articles.append(article)
            
    unique_articles.sort(key=lambda x: x['date'], reverse=True)
    return unique_articles

def get_rss_data(scholar_name):
    """Function to fetch all RSS data for a scholar that can be used by main.py"""
    articles = fetch_all_news()
    return {'media': articles}

if __name__ == "__main__":
    # For standalone testing
    SCHOLAR_NAME = "Professor Dr Jodie Rummer"
    rss_data = get_rss_data(SCHOLAR_NAME)
    
    # Save to file for testing
    test_file = os.path.join("scholar_data", f"{SCHOLAR_NAME.replace(' ', '_')}_rss.json")
    with open(test_file, "w") as f:
        json.dump(rss_data, f, indent=4)
    print(f"Saved {len(rss_data['media'])} media items to {test_file}") 