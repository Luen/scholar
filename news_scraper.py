import feedparser
import json
import re
import os
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, TypedDict, Literal, Set, Any, Union
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from email.utils import parsedate_to_datetime
import pytz
import hashlib
from pathlib import Path

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
REVALIDATE_TIME = 604800  # One week in seconds

# Cache configuration
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

SEARCH_KEYWORDS = [
    "Jodie Rummer",
    "Dr Jodie Rummer",
    "Dr. Jodie Rummer",
    "Professor Rummer",
    "Professor Jodie Rummer",
    "Professor Dr Jodie Rummer",
    "Rummer",
    "Rummerlab",
    "Physioshark",
    "James Cook University shark",
    "JCU shark research",
    "coral reef physiology",
    "marine biology JCU",
]

MARINE_KEYWORDS = [
    'marine', 'reef', 'shark', 'fish', 'ocean', 'coral', 
    'climate change', 'conservation', 'great barrier reef',
    'marine science', 'marine biology', 'aquatic', 'ecosystem',
    'marine life', 'marine conservation', 'marine research'
]

RSS_FEEDS = {
    'The Conversation': 'https://theconversation.com/profiles/jodie-l-rummer-711270/articles.atom',
    'ABC News': 'https://www.abc.net.au/news/feed/51120/rss.xml',
    'Science Daily': 'https://www.sciencedaily.com/rss/plants_animals/marine_biology.xml',
    'Yahoo News AU': 'https://au.news.yahoo.com/rss',
    'news.com.au': 'https://www.news.com.au/content-feeds/latest-news-national/',
    'ABC Science': 'https://www.abc.net.au/science/news/topic/enviro/enviro.xml',
    'News.com.au Science': 'http://feeds.news.com.au/public/rss/2.0/news_tech_506.xml',
    'Sydney Morning Herald': 'http://www.smh.com.au/rssheadlines/health/article/rss.xml',
    'SBS News': 'https://www.sbs.com.au/news/feed',
    'Cairns News': 'https://cairnsnews.org/feed/',
    'The Australian': 'https://www.theaustralian.com.au/feed',
    'Brisbane Times': 'https://www.brisbanetimes.com.au/rss/feed.xml',
    'The Age': 'https://www.theage.com.au/rss/feed.xml',
    'WA Today': 'https://www.watoday.com.au/rss/feed.xml',
    'Nature Asia Pacific': 'https://www.nature.com/nature.rss',
    'CSIRO News': 'https://www.csiro.au/en/News/News-releases/All-news-releases.feed',
    'Google News': 'https://news.google.com/rss/search?q=Jodie+Rummer+OR+Great+Barrier+Reef+OR+James+Cook+University&hl=en-AU&gl=AU&ceid=AU:en'
}

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
    keywords: Optional[List[str]]  # New field to track matching keywords

def strip_html(html: str) -> str:
    """Remove HTML tags and entities from text."""
    if not html:
        return ''
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html)
    # Remove HTML entities
    text = re.sub(r'&[^;]+;', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove "Exclusive:" or "Live:" prefix
    text = re.sub(r'^(Exclusive|Live):\s*', '', text, flags=re.IGNORECASE)
    return text.strip()

def find_matching_keywords(text: str) -> Set[str]:
    """Find all matching keywords in the text."""
    text = text.lower()
    return {keyword for keyword in SEARCH_KEYWORDS if keyword.lower() in text}

def does_article_mention_keywords(content: str, title: str, description: str) -> Set[str]:
    """Check if article mentions any keywords and return the matching ones."""
    normalized_content = f"{content} {title} {description}".lower()
    matching_keywords = find_matching_keywords(normalized_content)
    
    # If we found direct keyword matches, return them
    if matching_keywords:
        return matching_keywords
    
    # If no direct matches but contains marine keywords and mentions JCU/James Cook University,
    # consider it relevant
    if any(term.lower() in normalized_content for term in MARINE_KEYWORDS) and \
       any(term in normalized_content for term in ['jcu', 'james cook university']):
        return {'marine research'}
    
    return set()

def extract_image_from_content(content: str) -> Optional[str]:
    """Extract image URL from HTML content."""
    if not content:
        return None
    match = re.search(r'<img[^>]+src="([^">]+)"', content)
    return match.group(1) if match else None

def standardize_date(date_str: Optional[str]) -> str:
    """Convert various date formats to ISO 8601 format (YYYY-MM-DDThh:mm:ssZ)."""
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
                
        return datetime.now(pytz.UTC).isoformat().replace('+00:00', 'Z')
    except Exception as e:
        logger.error(f"Error standardizing date {date_str}: {e}")
        return datetime.now(pytz.UTC).isoformat().replace('+00:00', 'Z')

def get_cache_key(url: str, params: Optional[Dict] = None) -> str:
    """Generate a unique cache key for a URL and optional parameters."""
    key = url
    if params:
        key += json.dumps(params, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()

def get_cached_response(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get cached response if it exists and is not expired."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if not cache_file.exists():
        return None
        
    try:
        with cache_file.open('r') as f:
            cached = json.load(f)
            
        # Check if cache is expired
        if time.time() - cached['timestamp'] > REVALIDATE_TIME:
            return None
            
        return cached['data']
    except Exception as e:
        logger.error(f"Error reading cache file {cache_file}: {e}")
        return None

def save_to_cache(cache_key: str, data: Any) -> None:
    """Save response data to cache."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    try:
        with cache_file.open('w') as f:
            json.dump({
                'timestamp': time.time(),
                'data': data
            }, f)
    except Exception as e:
        logger.error(f"Error saving to cache file {cache_file}: {e}")

def cached_request(url: str, method: str = 'get', headers: Optional[Dict] = None, 
                  params: Optional[Dict] = None, timeout: int = 30) -> requests.Response:
    """Make a cached HTTP request."""
    cache_key = get_cache_key(url, params)
    cached = get_cached_response(cache_key)
    
    if cached is not None:
        logger.info(f"Using cached response for {url}")
        # Create a Response-like object from cached data
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(cached).encode()
        return response
        
    # Make the actual request
    response = requests.request(method, url, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    
    # Cache the response data
    try:
        data = response.json()
        save_to_cache(cache_key, data)
    except ValueError:
        # If response is not JSON, cache the text content
        save_to_cache(cache_key, response.text)
        
    return response

def fetch_rss_feed(url: str, source: str, headers=DEFAULT_HEADERS) -> List[MediaItem]:
    """Fetch and parse an RSS feed."""
    try:
        response = cached_request(url, headers=headers)
        feed = feedparser.parse(response.text)
        
        articles = []
        for item in feed.entries:
            content = getattr(item, 'content', [{}])[0].get('value', '') if hasattr(item, 'content') else ''
            description = getattr(item, 'description', '') or getattr(item, 'summary', '')
            
            # Check for keywords
            matching_keywords = does_article_mention_keywords(content, item.title, description)
            if not matching_keywords:
                continue
            
            # Get the most accurate date available
            date_str = item.get('published', '') or item.get('updated', '') or item.get('created', '')
            
            media_item: MediaItem = {
                'type': 'article',
                'source': source,
                'title': strip_html(item.title),
                'description': strip_html(description),
                'url': item.link,
                'date': standardize_date(date_str),
                'sourceType': source if source in ['The Guardian', 'The Conversation', 'ABC News', 'CNN'] else 'Other',
                'keywords': list(matching_keywords)
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
        logger.error(f"Error fetching {source} RSS feed: {str(e)}")
        return []

def fetch_guardian_articles() -> List[MediaItem]:
    api_key = os.getenv('THE_GUARDIAN_API_KEY')
    if not api_key:
        logger.warning("Guardian API key not found in environment variables")
        return []
        
    try:
        url = f"https://content.guardianapis.com/search"
        params = {
            'q': ' OR '.join(f'"{keyword}"' for keyword in SEARCH_KEYWORDS),
            'show-fields': 'headline,trailText,thumbnail,bodyText',
            'api-key': api_key
        }
        response = cached_request(url, params=params)
        data = response.json()
        
        articles = []
        for article in data['response']['results']:
            matching_keywords = does_article_mention_keywords(
                article['fields'].get('bodyText', ''),
                article['fields'].get('headline', ''),
                article['fields'].get('trailText', '')
            )
            
            if not matching_keywords:
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
                'sourceType': 'The Guardian',
                'keywords': list(matching_keywords)
            }
            
            if article['fields'].get('thumbnail'):
                media_item['image'] = {
                    'url': article['fields']['thumbnail'],
                    'alt': strip_html(article['fields']['headline'])
                }
                
            articles.append(media_item)
            
        return articles
    except Exception as e:
        logger.error(f"Error fetching Guardian articles: {str(e)}")
        return []

def fetch_google_search(query: str) -> List[Dict]:
    """Fetch results from Google Custom Search API."""
    api_key = os.getenv("GOOGLE_API_KEY")
    cx_id = os.getenv("GOOGLE_CX_ID")
    
    if not (api_key and cx_id):
        logger.warning("Google Search API credentials not found")
        return []
        
    try:
        url = f"https://www.googleapis.com/customsearch/v1"
        params = {
            'q': query,
            'key': api_key,
            'cx': cx_id,
            'num': 10  # Maximum results per request
        }
        
        response = cached_request(url, params=params)
        return response.json().get("items", [])
    except Exception as e:
        logger.error(f"Error in Google Search API: {str(e)}")
        return []

def scrape_web_content(url: str) -> List[Dict]:
    """Scrape news content from a webpage."""
    try:
        response = cached_request(url, headers=MODERN_HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []
        
        # Look for article elements
        for article in soup.find_all(['article', 'div'], class_=lambda x: x and any(term in x.lower() for term in ['article', 'story', 'news-item'])):
            title_elem = article.find(['h1', 'h2', 'h3', 'h4'])
            link_elem = article.find('a')
            date_elem = article.find(attrs={'datetime': True}) or article.find(class_=lambda x: x and 'date' in x.lower())
            desc_elem = article.find(['p', 'div'], class_=lambda x: x and any(term in str(x).lower() for term in ['desc', 'summary', 'excerpt']))
            
            if not (title_elem and link_elem):
                continue
                
            title = strip_html(title_elem.text)
            url = urljoin(response.url, link_elem['href'])
            date = date_elem['datetime'] if date_elem and 'datetime' in date_elem.attrs else date_elem.text if date_elem else None
            description = strip_html(desc_elem.text) if desc_elem else ''
            
            articles.append({
                'title': title,
                'link': url,
                'date': date,
                'description': description
            })
            
        return articles
    except Exception as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        return []

def fetch_newsapi_articles() -> List[MediaItem]:
    """Fetch articles from NewsAPI."""
    api_key = os.getenv('NEWS_API_ORG_KEY')
    if not api_key:
        logger.warning('NEWS_API_ORG_KEY is not defined in environment variables')
        return []
    
    try:
        url = 'https://newsapi.org/v2/everything'
        # Create a complex query with all our keywords
        query = ' OR '.join([f'"{keyword}"' for keyword in SEARCH_KEYWORDS])
        params = {
            'q': query,
            'language': 'en',
            'sortBy': 'publishedAt',
            'pageSize': 100,  # Get more results
            'apiKey': api_key
        }
        
        response = cached_request(url, params=params, timeout=30)
        data = response.json()
        
        if not data.get('articles'):
            return []
        
        articles = []
        for article in data['articles']:
            matching_keywords = does_article_mention_keywords(
                article.get('content', ''),
                article.get('title', ''),
                article.get('description', '')
            )
            
            if not matching_keywords:
                continue
                
            media_item: MediaItem = {
                'type': 'article',
                'source': article['source']['name'],
                'title': strip_html(article['title']),
                'description': strip_html(article.get('description', '')),
                'url': article['url'],
                'date': standardize_date(article['publishedAt']),
                'sourceType': 'Other',
                'keywords': list(matching_keywords)
            }
            
            if article.get('urlToImage'):
                media_item['image'] = {
                    'url': article['urlToImage'],
                    'alt': strip_html(article['title'])
                }
            
            articles.append(media_item)
        
        return articles
    except Exception as e:
        logger.error(f'Error fetching NewsAPI articles: {e}')
        return []

def fetch_all_news() -> List[MediaItem]:
    """Fetch news from all sources and combine them."""
    all_articles = []
    
    # Fetch from RSS feeds
    for source, url in RSS_FEEDS.items():
        try:
            articles = fetch_rss_feed(url, source)
            all_articles.extend(articles)
            time.sleep(1)  # Be nice to the servers
        except Exception as e:
            logger.error(f"Error fetching {source}: {str(e)}")
    
    # Add Guardian articles
    try:
        articles = fetch_guardian_articles()
        all_articles.extend(articles)
        time.sleep(1)
    except Exception as e:
        logger.error(f"Error fetching Guardian articles: {str(e)}")
    
    # Add NewsAPI articles
    try:
        articles = fetch_newsapi_articles()
        all_articles.extend(articles)
        time.sleep(1)
    except Exception as e:
        logger.error(f"Error fetching NewsAPI articles: {str(e)}")
    
    # Add Google Search results
    try:
        for keyword in SEARCH_KEYWORDS:
            google_results = fetch_google_search(f'"{keyword}"')
            for item in google_results:
                matching_keywords = does_article_mention_keywords(
                    item.get('snippet', ''),
                    item.get('title', ''),
                    ''
                )
                
                if not matching_keywords:
                    continue
                    
                media_item: MediaItem = {
                    'type': 'article',
                    'source': 'Google Search',
                    'title': strip_html(item.get('title', '')),
                    'description': strip_html(item.get('snippet', '')),
                    'url': item.get('link', ''),
                    'date': standardize_date(None),
                    'sourceType': 'Other',
                    'keywords': list(matching_keywords)
                }
                
                if item.get('pagemap', {}).get('cse_image'):
                    media_item['image'] = {
                        'url': item['pagemap']['cse_image'][0]['src'],
                        'alt': strip_html(item.get('title', ''))
                    }
                    
                all_articles.append(media_item)
            time.sleep(2)  # Be extra nice to Google's API
    except Exception as e:
        logger.error(f"Error in Google Search: {str(e)}")

    # Add web scraping results
    news_sites = [
        'https://www.townsvillebulletin.com.au/news/townsville',
        'https://www.cairnspost.com.au/news/cairns',
        'https://www.abc.net.au/news/topic/marine-biology',
        'https://www.jcu.edu.au/news',
        'https://www.aims.gov.au/news-and-media',  # Australian Institute of Marine Science
        'https://www.gbrmpa.gov.au/news-room',     # Great Barrier Reef Marine Park Authority
        'https://www.coralcoe.org.au/news',        # ARC Centre of Excellence for Coral Reef Studies
        'https://nqherald.com.au/category/news/',  # North Queensland Register
    ]
    
    for site in news_sites:
        try:
            scraped_articles = scrape_web_content(site)
            for item in scraped_articles:
                matching_keywords = does_article_mention_keywords(
                    '',  # We don't have full content
                    item.get('title', ''),
                    item.get('description', '')
                )
                
                if not matching_keywords:
                    continue
                    
                media_item: MediaItem = {
                    'type': 'article',
                    'source': f"{urlparse(site).netloc} (Scraped)",
                    'title': strip_html(item.get('title', '')),
                    'description': strip_html(item.get('description', '')),
                    'url': item.get('link', ''),
                    'date': standardize_date(item.get('date')),
                    'sourceType': 'Other',
                    'keywords': list(matching_keywords)
                }
                all_articles.append(media_item)
            time.sleep(2)  # Be nice to the servers
        except Exception as e:
            logger.error(f"Error scraping {site}: {str(e)}")
            
    # Remove duplicates based on URL and sort by date
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        if article['url'] not in seen_urls:
            seen_urls.add(article['url'])
            unique_articles.append(article)
            
    unique_articles.sort(key=lambda x: x['date'], reverse=True)
    return unique_articles

def get_news_data(scholar_name: str) -> Dict[str, List[MediaItem]]:
    """Function to fetch all RSS data for a scholar that can be used by main.py"""
    articles = fetch_all_news()
    return {'media': articles}

if __name__ == "__main__":
    SCHOLAR_NAME = "Professor Dr Jodie Rummer"
    
    # For standalone testing
    rss_data = get_news_data(SCHOLAR_NAME)
    
    # Save to file for testing
    test_file = os.path.join("scholar_data", f"{SCHOLAR_NAME.replace(' ', '_')}_rss.json")
    os.makedirs("scholar_data", exist_ok=True)
    
    with open(test_file, "w") as f:
        json.dump(rss_data, f, indent=4)
    logger.info(f"Saved {len(rss_data['media'])} media items to {test_file}") 