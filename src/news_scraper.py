import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import pytz
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

try:
    from scrapling.fetchers import FetcherSession  # type: ignore

    _SCRAPLING_AVAILABLE = True
except Exception:  # pragma: no cover
    FetcherSession = None  # type: ignore
    _SCRAPLING_AVAILABLE = False

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
REVALIDATE_TIME = 604800  # One week in seconds

# Cache configuration (use CACHE_DIR env so Docker/server volume is used)
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Phrases used for NewsAPI / Guardian / Google Custom Search OR-queries only.
# Keep tight: broad terms ("marine biology JCU", "coral reef physiology") pull in unrelated pages.
NEWS_OR_QUERY_PHRASES = [
    "Jodie Rummer",
    "Dr Jodie Rummer",
    "Dr. Jodie Rummer",
    "Professor Jodie Rummer",
    "Associate Professor Jodie Rummer",
    "RummerLab",
    "Physioshark",
    "Physio shark",
    "Physiologyfish",
    "rummerjodie",
    "rummerlab",
    "@physioshark",
    "@rummerlab",
]

# Substrings for tagging items that already passed strict relevance (not used for inclusion).
TAG_PHRASES_FOR_KEYWORDS = [
    "Jodie Rummer",
    "RummerLab",
    "Physioshark",
    "Physiologyfish",
]

# Own-site hosts: drop from aggregated news/search results (external coverage only).
EXCLUDED_OWN_SITE_HOST_SUFFIXES = (
    "rummerlab.com",
    "jodierummer.com",
    "physioshark.org",
)

# Lab/personal social profiles and JCU portfolio (not third-party news articles).
_FACEBOOK_PAGE_SLUGS = frozenset({"jodie.rummer", "physioshark", "rummerlab"})
_INSTAGRAM_PROFILE_SLUGS = frozenset({"rummerjodie", "physioshark", "rummerlab"})
_X_PROFILE_SLUGS = frozenset({"physiologyfish", "physioshark", "rummerlab"})
_LINKEDIN_PROFILE_PREFIX = "/in/jodie-rummer"
_JCU_PORTFOLIO_PATH_PREFIX = "/researchers/jodie.rummer"


def _url_first_path_segment(path: str) -> str:
    segment = (path or "").strip("/").split("/", 1)[0].lower()
    return segment


def _url_is_excluded_social_or_profile(host: str, path: str) -> bool:
    if host in ("facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"):
        return _url_first_path_segment(path) in _FACEBOOK_PAGE_SLUGS
    if host in ("instagram.com", "www.instagram.com", "m.instagram.com"):
        return _url_first_path_segment(path) in _INSTAGRAM_PROFILE_SLUGS
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        path_lower = (path or "").lower()
        return path_lower.startswith(_LINKEDIN_PROFILE_PREFIX)
    if host in ("x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"):
        return _url_first_path_segment(path) in _X_PROFILE_SLUGS
    if host == "portfolio.jcu.edu.au":
        return (path or "").lower().startswith(_JCU_PORTFOLIO_PATH_PREFIX)
    return False


def url_is_excluded_own_site(url: str) -> bool:
    """
    True for lab/personal sites, social profiles, and JCU portfolio pages.

    External news articles (even on facebook.com elsewhere) are not excluded.
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        path = parsed.path or ""
    except ValueError:
        return False
    if not host:
        return False
    if any(
        host == suffix or host.endswith(f".{suffix}") for suffix in EXCLUDED_OWN_SITE_HOST_SUFFIXES
    ):
        return True
    return _url_is_excluded_social_or_profile(host, path)


# Exclude articles about Kirstein Rummery (different person)
EXCLUDE_KEYWORDS = [
    "kirstein rummery",
    "kirstein rummer",
    "kirstein r.",
    "kirstein r ",
    "edited by teppo kroger",
    "care poverty and unmet needs",
    "social care systems",
]

# Primary Rummer-related terms (lab, project names)
RUMMER_PRIMARY_KEYWORDS = ["rummerlab", "physioshark", "physiologyfish"]

RSS_FEEDS = {
    "The Conversation": "https://theconversation.com/profiles/jodie-l-rummer-711270/articles.atom",
    "ABC News": "https://www.abc.net.au/news/feed/51120/rss.xml",
    "Science Daily": "https://www.sciencedaily.com/rss/plants_animals/marine_biology.xml",
    "Yahoo News AU": "https://au.news.yahoo.com/rss",
    "news.com.au": "https://www.news.com.au/content-feeds/latest-news-national/",
    "ABC Science": "https://www.abc.net.au/science/news/topic/enviro/enviro.xml",
    "News.com.au Science": "http://feeds.news.com.au/public/rss/2.0/news_tech_506.xml",
    "Sydney Morning Herald": "http://www.smh.com.au/rssheadlines/health/article/rss.xml",
    "SBS News": "https://www.sbs.com.au/news/feed",
    "Cairns News": "https://cairnsnews.org/feed/",
    "Brisbane Times": "https://www.brisbanetimes.com.au/rss/feed.xml",
    "The Age": "https://www.theage.com.au/rss/feed.xml",
    "WA Today": "https://www.watoday.com.au/rss/feed.xml",
    "Nature Asia Pacific": "https://www.nature.com/nature.rss",
    "Google News": "https://news.google.com/rss/search?q=Jodie+Rummer+OR+Dr+Rummer+OR+RummerLab+OR+Physioshark&hl=en-AU&gl=AU&ceid=AU:en",
    "Oceanographic Magazine": "https://oceanographicmagazine.com/news/feed/",
    "Lab Down Under": "https://labdownunder.com/feed",
    "It's Rocket Science": "https://itsrocketscience.com.au/feed",
    "Ocean Conservancy": "https://oceanconservancy.org/feed",
    "Ocean Acidification ICC": "https://news-oceanacidification-icc.org/category/web-sites-and-blogs/feed/",
    "Oceanic Society": "https://oceanicsociety.org/feed",
}

DEFAULT_HEADERS = {
    "Accept": "application/atom+xml,application/xml,text/xml,application/rss+xml",
    "User-Agent": "Mozilla/5.0 (compatible; RummerLab/1.0; +https://rummerlab.org)",
}

MODERN_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.townsvillebulletin.com.au",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


class MediaItem(TypedDict):
    type: Literal["article"]
    source: str
    title: str
    description: str
    url: str
    date: str
    sourceType: str
    image: Optional[dict[str, str]]
    keywords: Optional[list[str]]


# Manual/custom media additions (curated, always included; deduped by URL/title)
CUSTOM_MEDIA_ADDITIONS: list[MediaItem] = [
    {
        "type": "article",
        "source": "Cairns Post",
        "title": "Cairns Post coverage",
        "description": "Media coverage featuring Dr. Jodie Rummer",
        "url": "",
        "date": "2026-01-16T00:00:00Z",
        "sourceType": "Other",
        "image": {
            "url": "/images/media/2026-01-16-Cairns-Post.jpg",
            "alt": "Cairns Post article featuring Dr. Jodie Rummer",
        },
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "Cairns Post",
        "title": "Far North Qld shark attack victim at Hull Heads identified as Michael Jensz",
        "description": "Professor Jodie Rummer said shark management needs to be evidence-based, not driven by fear or retaliation, after the fatal Hull Heads shark attack.",
        "url": "https://www.cairnspost.com.au/news/cassowary-coast/far-north-qld-shark-attack-victim-at-hull-heads-identified-as-michael-jensz/news-story/17a46d4315b000c949c1a45c73b14bbf?btr=e37276b29ff7a5945234d77f59479070&giftid=rFuQ7PdFn7",
        "date": "2026-05-25T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "news.com.au",
        "title": "Bob Katter calls for shark culling after horror attack leaves Cairns spearfisherman dead",
        "description": "Jodie Rummer said there is no scientifically robust justification for shark culling after the fatal Hull Heads shark-human interaction.",
        "url": "https://www.news.com.au/travel/travel-updates/incidents/bob-katter-calls-for-shark-culling-after-horror-attack-leaves-cairns-spearfisherman-dead/news-story/56ecba20db4aacb882e84930e8df0d33",
        "date": "2026-05-25T03:25:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "ABC News",
        "title": "Death of Michael Jensz in Qld shark attack brings dangers of spearfishing 'close to home'",
        "description": "Jodie Rummer disputed claims that shark numbers are increasing and said culling is not a solution after the fatal Far North Queensland spearfishing incident.",
        "url": "https://www.abc.net.au/news/2026-05-25/queensland-spearfisher-shark-attack-victim-identified/106718104",
        "date": "2026-05-25T06:52:03Z",
        "sourceType": "ABC News",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "DIVE Magazine",
        "title": "Great Barrier Reef spearfisher killed by shark bite",
        "description": "DIVE Magazine cited Jodie Rummer on evidence around shark-culling programmes after the fatal Kennedy Shoal spearfishing incident.",
        "url": "https://divemagazine.com/scuba-diving-news/great-barrier-reef-spearfisher-killed-by-shark-bite",
        "date": "2026-05-27T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "Courier Mail",
        "title": "Shark victim an action man",
        "description": "Print coverage of the Michael Jensz shark fatality quoting Jodie Rummer on evidence-based shark management and shark-human interactions.",
        "url": "",
        "date": "2026-05-26T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "print"],
    },
    {
        "type": "article",
        "source": "Cairns Post",
        "title": "DIED WITH MATES",
        "description": "Print coverage of the Hull Heads shark fatality quoting Jodie Rummer on shark behaviour, shark-human interactions, and evidence-based management.",
        "url": "",
        "date": "2026-05-26T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "print"],
    },
    {
        "type": "article",
        "source": "Townsville Bulletin",
        "title": "Cairns man identified as shark attack victim",
        "description": "Print coverage of the Kennedy Shoal shark fatality quoting Jodie Rummer on bull sharks, seasonal shark activity, and evidence-based shark management.",
        "url": "",
        "date": "2026-05-26T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "print"],
    },
    {
        "type": "article",
        "source": "Discover Wildlife",
        "title": "Walking sharks found off Australian coast",
        "description": '"Walking sharks" found off Australian coast. A closer look reveals extraordinary new discovery about epaulette shark reproduction.',
        "url": "https://www.discoverwildlife.com/animal-facts/marine-animals/epaulette-shark-reproduction",
        "date": "2026-01-15T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "ABC News",
        "title": "Captive epaulette sharks lay eggs using no extra energy, JCU research finds",
        "description": "Captive epaulette sharks lay eggs using no extra energy, JCU research finds",
        "url": "https://www.abc.net.au/news/2026-01-16/captive-epaulette-sharks-make-lay-eggs-using-no-extra-energy-jcu/106231990",
        "date": "2026-01-16T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "ABC News",
        "title": "Epaulette sharks are breaking the rules of biology",
        "description": "Epaulette sharks are breaking the rules of biology",
        "url": "https://www.abc.net.au/news/2026-01-16/epaulette-sharks-are-breaking-the-rules-of-biology/106229708",
        "date": "2026-01-16T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "The Conversation",
        "title": "Sharks freeze when you turn them upside down – and there's no good reason why",
        "description": "Research explores tonic immobility in sharks, rays and their relatives.",
        "url": "https://theconversation.com/sharks-freeze-when-you-turn-them-upside-down-and-theres-no-good-reason-why-259448",
        "date": "2025-06-23T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "ABC News",
        "title": "Highest number of January shark attacks in NSW for a decade, according to national database",
        "description": 'Jodie Rummer, a marine biology professor at James Cook University, says the recent spate of attacks "is even shocking to me".',
        "url": "https://www.abc.net.au/news/2026-01-21/shark-attack-numbers-in-nsw-australian-shark-incident-database/106249078",
        "date": "2026-01-21T00:00:00Z",
        "sourceType": "ABC News",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "Phys.org",
        "title": "Walking sharks break biology reproduction rules",
        "description": "JCU's shark physiology research team, led by Professor Jodie Rummer, finds that walking sharks can reproduce and lay eggs without any measurable rise in energy use.",
        "url": "https://phys.org/news/2026-01-sharks-biology-reproduction.html",
        "date": "2026-01-21T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "Australasian Leisure Management Magazine",
        "title": "NSW shark incidents highlight challenges for Coastal Safety, Risk Communication and Beach Management",
        "description": 'Professor Rummer highlighted "It is important to frame these as shark–human interactions rather than deliberate attacks. Sharks do not target people."',
        "url": "https://www.ausleisure.com.au/news/nsw-shark-incidents-highlight-challenges-for-coastal-safety-risk-communication-and-beach-management",
        "date": "2026-01-21T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "Tech Explorist",
        "title": "Walking sharks break the rules of reproductive energy costs",
        "description": "Research by Professor Jodie Rummer assessing the metabolic and physiological costs of oviparity in the epaulette shark (Hemiscyllium ocellatum).",
        "url": "https://www.techexplorist.com/walking-sharks-break-rules-reproductive-energy-costs/101872/",
        "date": "2026-01-21T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "Green Matters",
        "title": "These Walking Sharks Defy Biology's Reproduction Rules, Scientists Reveal",
        "description": "Professor Rummer, who led James Cook University's shark physiology research team, said there was no uptick in energy use during reproduction.",
        "url": "https://www.greenmatters.com/pn/these-walking-sharks-defy-biologys-reproduction-rules-scientists-reveal",
        "date": "2026-01-21T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    },
    {
        "type": "article",
        "source": "Oceanographic Magazine",
        "title": "Epaulette shark research in Oceanographic Magazine",
        "description": "Feature coverage of RummerLab epaulette shark research highlighting the team's long-running work on climate change, reef sharks, and accessible ocean science.",
        "url": "https://www.oceanographicmagazine.com/",
        "date": "2021-10-22T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "epaulette", "print"],
    },
    {
        "type": "article",
        "source": "Sydney Morning Herald",
        "title": "Science trails the tales of city's bull sharks",
        "description": "Syndicated coverage quoting Jodie Rummer on warming waters, bull shark movements, and the importance of healthy shark populations in healthy marine ecosystems.",
        "url": "",
        "date": "2024-02-01T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "print"],
    },
    {
        "type": "article",
        "source": "Brisbane Times / SMH / The Age / WA Today",
        "title": "Shark diaries: Where did Lucy, Bruce and Paulie the bull sharks go this week?",
        "description": "Online syndicated coverage quoting Jodie Rummer on bull shark migration, warm Sydney waters, and shark conservation.",
        "url": "",
        "date": "2024-01-31T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "online"],
    },
    {
        "type": "article",
        "source": "ABC Radio Queensland",
        "title": "Professor Jodie Rummer on Cyclone Kirrily and reef climate impacts",
        "description": "ABC Radio Queensland interview discussing Cyclone Kirrily, climate impacts, and the Great Barrier Reef.",
        "url": "https://youtu.be/G0Khf32LHEQ",
        "date": "2024-01-31T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "audio", "youtube"],
    },
    {
        "type": "article",
        "source": "WIN News",
        "title": "Coral reefs and conference coverage featuring Dr Jodie Rummer",
        "description": "Regional WIN News coverage from the Australian Coral Reef Society conference in Townsville, featuring Jodie Rummer as ACRS President on coral reefs and climate action.",
        "url": "",
        "date": "2025-09-17T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom", "tv"],
    },
]


def strip_html(html: str) -> str:
    """Remove HTML tags and entities from text."""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
    except Exception:
        text = html
    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove HTML entities
    text = re.sub(r"&[^;]+;", "", text)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove "Exclusive:" or "Live:" prefix
    text = re.sub(r"^(Exclusive|Live):\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _is_about_kirstein_rummery(content: str, title: str, description: str) -> bool:
    """Exclude articles about Kirstein Rummery (different person)."""
    combined = f"{content} {title} {description}".lower()
    return any(kw in combined for kw in EXCLUDE_KEYWORDS)


# Marine / institutional context: "Professor Rummer" in reef press often omits "Jodie" in the title.
_RUMMER_MARINE_CONTEXT_TERMS = (
    "jcu",
    "james cook",
    "shark",
    "marine",
    "coral",
    "reef",
    "fish",
    "epaulette",
    "physiolog",
    "great barrier",
    "barrier reef",
    "climate",
    "ocean",
    "moorea",
    "queensland",
    "townsville",
    "gb reef",
    "gbr",
)

# When "Jodie" is absent, reject obvious non-marine / wrong-person hits.
_RUMMER_FALSE_POSITIVE_WHEN_NO_JODIE = (
    "eecs mourns",
    "electrical engineering and computer",
    "obituary",
    "passed away",
    "merriam-webster",
    "definition of rummer",
    "large-bowled",
    "drinking glass",
    "prunts",
    "second rummer up",
    "rummer development",
    "mid-century homes",
    "bob rummer",
)


def _collapsed_alnum(text: str) -> str:
    """Lowercase and strip spaces/hyphens/underscores for handle-style matches."""
    return re.sub(r"[\s\-_]+", "", text.lower())


def does_article_mention_rummer(content: str, title: str, description: str) -> bool:
    """
    True only when the piece is plausibly about Dr Jodie Rummer, RummerLab, or Physioshark.

    Intentionally rejects: generic JCU marine/shark news, other people's obituaries,
    dictionary 'rummer' (drinking glass), and unrelated 'Professor Rummer' mentions.
    """
    combined = f"{content} {title} {description}".lower()
    title_l, desc_l = title.lower(), description.lower()

    if _is_about_kirstein_rummery(content, title, description):
        return False

    if "jodie" not in combined and any(
        fp in combined for fp in _RUMMER_FALSE_POSITIVE_WHEN_NO_JODIE
    ):
        return False

    collapsed = _collapsed_alnum(f"{content}{title}{description}")
    if "rummerlab" in collapsed or "physioshark" in collapsed or "physiologyfish" in collapsed:
        return True

    if "jodie" in combined and re.search(r"\brummer\b", combined):
        return True

    if "rummerjodie" in collapsed:
        return True

    if re.search(r"\b(dr\.?|professor|prof\.?)\s+rummer\b", combined) and any(
        ctx in combined for ctx in _RUMMER_MARINE_CONTEXT_TERMS
    ):
        return True

    if re.search(r"\bassociate\s+professor\s+rummer\b", combined) and (
        "jodie" in combined or any(ctx in combined for ctx in _RUMMER_MARINE_CONTEXT_TERMS)
    ):
        return True

    if any(kw in combined or kw in title_l or kw in desc_l for kw in RUMMER_PRIMARY_KEYWORDS):
        return True

    return False


def does_article_mention_keywords(content: str, title: str, description: str) -> set[str]:
    """Return display tags only for items that pass strict Dr Jodie Rummer relevance."""
    if _is_about_kirstein_rummery(content, title, description):
        return set()
    if not does_article_mention_rummer(content, title, description):
        return set()
    combined = f"{content} {title} {description}".lower()
    tags = {p for p in TAG_PHRASES_FOR_KEYWORDS if p.lower() in combined}
    if tags:
        return tags
    return {"Jodie Rummer"}


def is_likely_english(text: str | None) -> bool:
    """Filter out non-English articles (e.g. Spanish « » or ¿)."""
    if not text:
        return False
    return not ((text.count("«") and text.count("»")) or (text.count("¿") and text.count("?")))


def extract_image_from_content(content: str) -> str | None:
    """Extract image URL from HTML content."""
    if not content:
        return None
    match = re.search(r'<img[^>]+src="([^">]+)"', content)
    return match.group(1) if match else None


def extract_image_from_html(html: str, base_url: str) -> str | None:
    """Extract article image from HTML (og:image, twitter:image, img tags)."""
    if not html:
        return None
    patterns = [
        r'<meta[^>]*(?:property|name)=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
        r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']og:image["\']',
        r'<meta[^>]*name=["\']twitter:image(?::src)?["\'][^>]*content=["\']([^"\']+)["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        match = re.search(pat, html, re.I)
        if match and match.group(1):
            url = match.group(1).replace("&amp;", "&")
            if any(x in url.lower() for x in ["logo", "icon", "avatar", "placeholder"]):
                continue
            if url.startswith("/"):
                parsed = urlparse(base_url)
                url = f"{parsed.scheme}://{parsed.netloc}{url}"
            elif not url.startswith("http"):
                url = urljoin(base_url, url)
            return url
    return None


def standardize_date(date_str: Optional[str]) -> str:
    """Convert various date formats to ISO 8601 format (YYYY-MM-DDThh:mm:ssZ)."""
    if not date_str:
        return datetime.now(pytz.UTC).isoformat().replace("+00:00", "Z")

    try:
        # Try parsing as RFC 2822 (common in RSS feeds)
        try:
            dt = parsedate_to_datetime(date_str)
            return dt.astimezone(pytz.UTC).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError):
            pass

        # Try parsing as ISO format
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.astimezone(pytz.UTC).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError):
            pass

        # Try common formats
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
        ]:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.UTC)
                return dt.astimezone(pytz.UTC).isoformat().replace("+00:00", "Z")
            except (ValueError, TypeError):
                continue

        return datetime.now(pytz.UTC).isoformat().replace("+00:00", "Z")
    except Exception as e:
        logger.error(f"Error standardizing date {date_str}: {e}")
        return datetime.now(pytz.UTC).isoformat().replace("+00:00", "Z")


def get_cache_key(url: str, params: dict | None = None) -> str:
    """Generate a unique cache key for a URL and optional parameters (not a security digest)."""
    key = url
    if params:
        key += json.dumps(params, sort_keys=True)
    # BLAKE2b avoids CodeQL "weak hash on sensitive data" on URL strings; suffices for filenames.
    return hashlib.blake2b(key.encode(), digest_size=32).hexdigest()


def get_cached_response(cache_key: str) -> dict[str, Any] | None:
    """Get cached response if it exists and is not expired."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if not cache_file.exists():
        return None

    try:
        with cache_file.open("r") as f:
            cached = json.load(f)

        # Check if cache is expired
        if time.time() - cached["timestamp"] > REVALIDATE_TIME:
            return None

        return cached["data"]
    except Exception as e:
        logger.error(f"Error reading cache file {cache_file}: {e}")
        return None


def save_to_cache(cache_key: str, data: Any) -> None:
    """Save response data to cache."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    try:
        with cache_file.open("w") as f:
            json.dump({"timestamp": time.time(), "data": data}, f)
    except Exception as e:
        logger.error(f"Error saving to cache file {cache_file}: {e}")


def fetch_with_retry(
    url: str,
    method: str = "get",
    headers: dict | None = None,
    params: dict | None = None,
    timeout: int = 30,
    retries: int = 3,
) -> requests.Response | None:
    """Make HTTP request with retries."""
    for attempt in range(retries):
        try:
            resp = requests.request(
                method=method, url=url, headers=headers, params=params, timeout=timeout
            )
            return resp
        except requests.RequestException as e:
            if attempt < retries - 1:
                logger.warning(f"Retrying {url}, {retries - attempt - 1} attempts left: {e}")
                time.sleep(1)
            else:
                logger.error(f"Final request error for {url}: {e}")
                return None
    return None


def cached_request(
    url: str,
    method: str = "get",
    headers: dict | None = None,
    params: dict | None = None,
    timeout: int = 30,
) -> requests.Response:
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

    def _scrapling_fallback() -> requests.Response:
        """
        Fallback fetch using Scrapling's static engine (browser-like TLS + headers).
        This helps with 403 blocks and some local SSL chain issues.
        """
        if not _SCRAPLING_AVAILABLE or FetcherSession is None:
            raise RuntimeError("Scrapling is not available")
        if method.lower() != "get":
            raise RuntimeError("Scrapling fallback only supports GET")

        # Build the final URL including query params.
        final_url = url
        if params:
            final_url = requests.Request("GET", url, params=params).prepare().url  # type: ignore[assignment]

        # Merge headers: caller headers win.
        merged_headers = dict(DEFAULT_HEADERS)
        if headers:
            merged_headers.update(headers)

        with FetcherSession(
            impersonate="chrome",
            timeout=timeout,
            stealthy_headers=True,
            follow_redirects=True,
            retries=2,
            retry_delay=1,
            headers=merged_headers,
            verify=True,
        ) as s:
            resp = s.get(final_url)

        response = requests.Response()
        response.status_code = int(getattr(resp, "status_code", 0) or 0)
        response.url = final_url
        response._content = (getattr(resp, "text", "") or "").encode("utf-8", errors="ignore")
        # Best-effort headers
        try:
            response.headers.update(getattr(resp, "headers", {}) or {})
        except Exception:
            pass
        response.raise_for_status()
        return response

    # Make the actual request
    try:
        response = requests.request(method, url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        # Only fallback on cases where a browser-like client may help.
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (403, 429) or isinstance(e, requests.exceptions.SSLError):
            logger.warning("requests failed for %s (%s); trying Scrapling fallback", url, e)
            response = _scrapling_fallback()
        else:
            raise

    # Cache the response data
    try:
        data = response.json()
        save_to_cache(cache_key, data)
    except ValueError:
        # If response is not JSON, cache the text content
        save_to_cache(cache_key, response.text)

    return response


def fetch_rss_feed(url: str, source: str, headers=None) -> list[MediaItem]:
    """Fetch and parse an RSS feed."""
    if headers is None:
        headers = DEFAULT_HEADERS
    try:
        response = cached_request(url, headers=headers)
        feed = feedparser.parse(response.text)

        articles = []
        for item in feed.entries:
            content = (
                getattr(item, "content", [{}])[0].get("value", "")
                if hasattr(item, "content")
                else ""
            )
            description = getattr(item, "description", "") or getattr(item, "summary", "")

            matching_keywords = does_article_mention_keywords(content, item.title, description)
            # Filter non-English articles (e.g. The Conversation can have multilingual)
            if source == "The Conversation" and not is_likely_english(item.title):
                continue

            if not matching_keywords:
                continue

            # Get the most accurate date available
            date_str = (
                item.get("published", "") or item.get("updated", "") or item.get("created", "")
            )

            media_item: MediaItem = {
                "type": "article",
                "source": source,
                "title": strip_html(item.title),
                "description": strip_html(description),
                "url": item.link,
                "date": standardize_date(date_str),
                "sourceType": source
                if source in ["The Guardian", "The Conversation", "ABC News", "CNN"]
                else "Other",
                "keywords": list(matching_keywords),
            }

            # Add image if available
            if hasattr(item, "enclosures") and item.enclosures:
                enclosure = item.enclosures[0]
                if "url" in enclosure:
                    media_item["image"] = {"url": enclosure.url, "alt": strip_html(item.title)}
            elif content:
                image_url = extract_image_from_content(content)
                if image_url:
                    media_item["image"] = {"url": image_url, "alt": strip_html(item.title)}

            articles.append(media_item)

        return articles
    except Exception as e:
        logger.error(f"Error fetching {source} RSS feed: {str(e)}")
        return []


# News site base URLs for Newspaper4k source discovery (build + parse articles)
NEWSPAPER4K_SOURCE_URLS = [
    "https://www.abc.net.au/news",
    "https://www.jcu.edu.au/news",
    "https://www.aims.gov.au",
    "https://cosmosmagazine.com",
    "https://theconversation.com",
]
NEWSPAPER4K_ARTICLES_PER_SOURCE = 15
NEWSPAPER4K_NUMBER_THREADS = 2


def fetch_newspaper4k_articles() -> list[MediaItem]:
    """Discover and parse articles from news sources using Newspaper4k."""
    try:
        import newspaper
    except ImportError:
        logger.warning("newspaper4k not installed; skip Newspaper4k sources")
        return []

    articles: list[MediaItem] = []
    for source_url in NEWSPAPER4K_SOURCE_URLS:
        try:
            source_name = urlparse(source_url).netloc or source_url
            paper = newspaper.build(
                source_url,
                language="en",
                number_threads=NEWSPAPER4K_NUMBER_THREADS,
            )
            paper.build()  # populate article list from front page / categories / RSS
            for art in paper.articles[:NEWSPAPER4K_ARTICLES_PER_SOURCE]:
                try:
                    art.download()
                    art.parse()
                    if not getattr(art, "title", None) and not getattr(art, "text", None):
                        continue
                    content = (art.text or "")[:5000]
                    title = (art.title or "").strip()
                    description = (art.summary or art.text or "")[:500].strip() if art.text else ""
                    matching_keywords = does_article_mention_keywords(content, title, description)
                    if not matching_keywords:
                        continue
                    date_val = getattr(art, "publish_date", None)
                    date_str = date_val.isoformat() if date_val is not None else None
                    media_item: MediaItem = {
                        "type": "article",
                        "source": f"{source_name} (Newspaper4k)",
                        "title": strip_html(title),
                        "description": strip_html(description),
                        "url": art.url,
                        "date": standardize_date(date_str),
                        "sourceType": "Other",
                        "keywords": list(matching_keywords),
                    }
                    if getattr(art, "top_image", None):
                        media_item["image"] = {
                            "url": art.top_image,
                            "alt": strip_html(title),
                        }
                    else:
                        media_item["image"] = None
                    articles.append(media_item)
                except Exception as e:
                    logger.debug(f"Newspaper4k parse skip {getattr(art, 'url', '')}: {e}")
                time.sleep(0.5)
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error building Newspaper4k source {source_url}: {e}")
    return articles


def fetch_guardian_articles() -> list[MediaItem]:
    api_key = os.getenv("THE_GUARDIAN_API_KEY")
    if not api_key:
        logger.warning("Guardian API key not found in environment variables")
        return []

    try:
        url = "https://content.guardianapis.com/search"
        params = {
            "q": " OR ".join(f'"{phrase}"' for phrase in NEWS_OR_QUERY_PHRASES),
            "show-fields": "headline,trailText,thumbnail,bodyText",
            "api-key": api_key,
        }
        response = cached_request(url, params=params)
        data = response.json()

        articles = []
        for article in data["response"]["results"]:
            matching_keywords = does_article_mention_keywords(
                article["fields"].get("bodyText", ""),
                article["fields"].get("headline", ""),
                article["fields"].get("trailText", ""),
            )

            if not matching_keywords:
                continue

            # Skip blog posts and live updates
            if any(
                term in article["fields"].get("headline", "").lower()
                for term in [
                    "live updates",
                    "as it happened",
                    "live blog",
                    "live coverage",
                    "live report",
                    "live reaction",
                    "live news",
                    "crossword",
                ]
            ):
                continue

            media_item: MediaItem = {
                "type": "article",
                "source": "The Guardian",
                "title": strip_html(article["fields"]["headline"]),
                "description": strip_html(article["fields"].get("trailText", "")),
                "url": article["webUrl"],
                "date": article["webPublicationDate"],
                "sourceType": "The Guardian",
                "keywords": list(matching_keywords),
            }

            if article["fields"].get("thumbnail"):
                media_item["image"] = {
                    "url": article["fields"]["thumbnail"],
                    "alt": strip_html(article["fields"]["headline"]),
                }

            articles.append(media_item)

        return articles
    except Exception as e:
        logger.error(f"Error fetching Guardian articles: {str(e)}")
        return []


# GNews (Google News API) config: country AU, English, last 7 days
GNEWS_MAX_RESULTS = 50
GNEWS_PERIOD = "7d"


def fetch_gnews_articles() -> list[MediaItem]:
    """Fetch articles from Google News via the GNews package (keeps RSS Google News as well)."""
    try:
        from gnews import GNews
    except ImportError:
        logger.warning("gnews not installed; skip GNews source")
        return []

    articles: list[MediaItem] = []
    try:
        google_news = GNews(
            language="en",
            country="AU",
            period=GNEWS_PERIOD,
            max_results=GNEWS_MAX_RESULTS,
        )
        # Query with main Rummer / lab terms (same theme as the existing Google News RSS)
        query = '"Jodie Rummer" OR RummerLab OR Physioshark OR "Dr Jodie Rummer"'
        raw = google_news.get_news(query)
        if not raw:
            return articles
        for item in raw:
            title = (item.get("title") or "").strip()
            description = (item.get("description") or "").strip()
            url = (item.get("url") or "").strip()
            if not url or not title:
                continue
            published = item.get("published date") or item.get("published_date") or ""
            matching_keywords = does_article_mention_keywords(description, title, "")
            if not matching_keywords:
                continue
            publisher = (item.get("publisher") or "GNews").strip()
            media_item: MediaItem = {
                "type": "article",
                "source": "GNews",
                "title": strip_html(title),
                "description": strip_html(description)
                or (f"Source: {publisher}" if publisher else ""),
                "url": url,
                "date": standardize_date(published),
                "sourceType": "GNews",
                "keywords": list(matching_keywords),
            }
            media_item["image"] = None
            articles.append(media_item)
        return articles
    except Exception as e:
        logger.error(f"Error fetching GNews articles: {e}")
        return []


def fetch_google_search(query: str) -> list[dict]:
    """Fetch results from Google Custom Search API."""
    api_key = os.getenv("GOOGLE_API_KEY")
    cx_id = os.getenv("GOOGLE_CX_ID")

    if not (api_key and cx_id):
        logger.warning("Google Search API credentials not found")
        return []

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": query,
            "key": api_key,
            "cx": cx_id,
            "num": 10,  # Maximum results per request
        }

        response = cached_request(url, params=params)
        return response.json().get("items", [])
    except Exception as e:
        logger.error(f"Error in Google Search API: {str(e)}")
        return []


def scrape_web_content(url: str) -> list[dict]:
    """Scrape news content from a webpage."""
    try:
        response = cached_request(url, headers=MODERN_HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        articles = []

        # Look for article elements
        for article in soup.find_all(
            ["article", "div"],
            class_=lambda x: (
                x and any(term in x.lower() for term in ["article", "story", "news-item"])
            ),
        ):
            title_elem = article.find(["h1", "h2", "h3", "h4"])
            link_elem = article.find("a")
            date_elem = article.find(attrs={"datetime": True}) or article.find(
                class_=lambda x: x and "date" in x.lower()
            )
            desc_elem = article.find(
                ["p", "div"],
                class_=lambda x: (
                    x and any(term in str(x).lower() for term in ["desc", "summary", "excerpt"])
                ),
            )

            if not (title_elem and link_elem):
                continue

            title = strip_html(title_elem.text)
            url = urljoin(response.url, link_elem["href"])
            date = (
                date_elem["datetime"]
                if date_elem and "datetime" in date_elem.attrs
                else date_elem.text
                if date_elem
                else None
            )
            description = strip_html(desc_elem.text) if desc_elem else ""

            articles.append({"title": title, "link": url, "date": date, "description": description})

        return articles
    except Exception as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        return []


def fetch_newsapi_articles() -> list[MediaItem]:
    """Fetch articles from NewsAPI."""
    api_key = os.getenv("NEWS_API_ORG_KEY")
    if not api_key:
        logger.warning("NEWS_API_ORG_KEY is not defined in environment variables")
        return []

    try:
        url = "https://newsapi.org/v2/everything"
        # Create a complex query with all our keywords
        query = " OR ".join(f'"{phrase}"' for phrase in NEWS_OR_QUERY_PHRASES)
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 100,  # Get more results
            "apiKey": api_key,
        }

        response = cached_request(url, params=params, timeout=30)
        data = response.json()

        if not data.get("articles"):
            return []

        articles = []
        for article in data["articles"]:
            matching_keywords = does_article_mention_keywords(
                article.get("content", ""), article.get("title", ""), article.get("description", "")
            )

            if not matching_keywords:
                continue

            media_item: MediaItem = {
                "type": "article",
                "source": article["source"]["name"],
                "title": strip_html(article["title"]),
                "description": strip_html(article.get("description", "")),
                "url": article["url"],
                "date": standardize_date(article["publishedAt"]),
                "sourceType": "Other",
                "keywords": list(matching_keywords),
            }

            if article.get("urlToImage"):
                media_item["image"] = {
                    "url": article["urlToImage"],
                    "alt": strip_html(article["title"]),
                }

            articles.append(media_item)

        return articles
    except Exception as e:
        logger.error(f"Error fetching NewsAPI articles: {e}")
        return []


def fetch_all_news(existing_urls: set[str] | None = None) -> list[MediaItem]:
    """Fetch news from all sources and combine them."""
    all_articles = list(CUSTOM_MEDIA_ADDITIONS)  # Manual additions first (win on URL/title dedup)

    enable_google_search = os.getenv("NEWS_ENABLE_GOOGLE_SEARCH", "0") == "1"
    enable_newspaper4k = os.getenv("NEWS_ENABLE_NEWSPAPER4K", "0") == "1"
    enable_web_scrape = os.getenv("NEWS_ENABLE_WEB_SCRAPE", "0") == "1"

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
    if enable_google_search:
        try:
            for phrase in NEWS_OR_QUERY_PHRASES:
                google_results = fetch_google_search(f'"{phrase}"')
                for item in google_results:
                    matching_keywords = does_article_mention_keywords(
                        item.get("snippet", ""), item.get("title", ""), ""
                    )

                    if not matching_keywords:
                        continue

                    media_item: MediaItem = {
                        "type": "article",
                        "source": "Google Search",
                        "title": strip_html(item.get("title", "")),
                        "description": strip_html(item.get("snippet", "")),
                        "url": item.get("link", ""),
                        "date": standardize_date(None),
                        "sourceType": "Other",
                        "keywords": list(matching_keywords),
                    }

                    if item.get("pagemap", {}).get("cse_image"):
                        media_item["image"] = {
                            "url": item["pagemap"]["cse_image"][0]["src"],
                            "alt": strip_html(item.get("title", "")),
                        }

                    all_articles.append(media_item)
                time.sleep(2)  # Be extra nice to Google's API
        except Exception as e:
            logger.error(f"Error in Google Search: {str(e)}")

    # Add GNews (Google News via GNews package; RSS Google News is kept above)
    try:
        articles = fetch_gnews_articles()
        all_articles.extend(articles)
        time.sleep(1)
    except Exception as e:
        logger.error(f"Error fetching GNews articles: {str(e)}")

    # Add Newspaper4k-discovered articles
    if enable_newspaper4k:
        try:
            articles = fetch_newspaper4k_articles()
            all_articles.extend(articles)
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error fetching Newspaper4k articles: {str(e)}")

    # Add web scraping results
    if enable_web_scrape:
        news_sites = [
            "https://www.townsvillebulletin.com.au/news/townsville",
            "https://www.cairnspost.com.au/news/cairns",
            "https://www.abc.net.au/news/topic/marine-biology",
            "https://www.jcu.edu.au/news",
            "https://www.aims.gov.au/news-and-media",  # Australian Institute of Marine Science
            "https://www.gbrmpa.gov.au/news-room",  # Great Barrier Reef Marine Park Authority
            "https://www.coralcoe.org.au/news",  # ARC Centre of Excellence for Coral Reef Studies
            "https://nqherald.com.au/category/news/",  # North Queensland Register
        ]

        for site in news_sites:
            try:
                scraped_articles = scrape_web_content(site)
                for item in scraped_articles:
                    matching_keywords = does_article_mention_keywords(
                        "",  # We don't have full content
                        item.get("title", ""),
                        item.get("description", ""),
                    )

                    if not matching_keywords:
                        continue

                    media_item: MediaItem = {
                        "type": "article",
                        "source": f"{urlparse(site).netloc} (Scraped)",
                        "title": strip_html(item.get("title", "")),
                        "description": strip_html(item.get("description", "")),
                        "url": item.get("link", ""),
                        "date": standardize_date(item.get("date")),
                        "sourceType": "Other",
                        "keywords": list(matching_keywords),
                    }
                    all_articles.append(media_item)
                time.sleep(2)  # Be nice to the servers
            except Exception as e:
                logger.error(f"Error scraping {site}: {str(e)}")

    # Deduplicate with source priorities (lower = higher priority).
    # Custom additions should win over fetched duplicates, then source rank breaks ties
    # within the custom/fetched groups.
    source_priorities: dict[str, int] = {
        "Cairns Post": 0,
        "Discover Wildlife": 0,
        "The Conversation": 1,
        "The Guardian": 2,
        "ABC News": 4,
        "Lab Down Under": 5,
        "It's Rocket Science": 6,
        "Ocean Conservancy": 7,
        "Ocean Acidification ICC": 8,
        "Oceanic Society": 9,
        "Oceanographic Magazine": 10,
        "Google News": 11,
        "GNews": 12,
        "NewsAPI": 13,
        "Newspaper4k": 14,
    }
    default_priority = 15
    tracking_query_params = {
        "btr",
        "fbclid",
        "gclid",
        "giftid",
        "igshid",
        "mc_cid",
        "mc_eid",
    }

    def normalize_title(t: str) -> str:
        t = t.lower()
        t = re.sub(r"\s*[-–—]\s*[^-–—]+$", "", t)
        t = re.sub(r"[^\w\s]", "", t)
        return t.strip()

    def is_tracking_query_param(name: str) -> bool:
        lowered = name.lower()
        return lowered in tracking_query_params or lowered.startswith("utm_")

    def normalize_url(url: str) -> str:
        """Normalize article URLs enough to catch common tracking-only variants."""
        stripped = url.strip()
        if not stripped:
            return ""
        try:
            parsed = urlparse(stripped)
            if not parsed.scheme or not parsed.netloc:
                return stripped
            path = parsed.path or "/"
            if path != "/":
                path = path.rstrip("/")
            query = urlencode(
                sorted(
                    (key, value)
                    for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                    if not is_tracking_query_param(key)
                )
            )
            return urlunparse(
                (
                    parsed.scheme.lower(),
                    parsed.netloc.lower().rstrip("."),
                    path,
                    "",
                    query,
                    "",
                )
            )
        except ValueError:
            return stripped

    def source_priority(source: str) -> int:
        if source.endswith(" (Newspaper4k)"):
            return source_priorities["Newspaper4k"]
        return source_priorities.get(source, default_priority)

    custom_article_signatures = {
        (normalize_title(article["title"]), normalize_url(article["url"]), article["source"])
        for article in CUSTOM_MEDIA_ADDITIONS
    }

    def dedupe_priority(article: MediaItem) -> tuple[int, int]:
        signature = (
            normalize_title(article["title"]),
            normalize_url(article["url"]),
            article["source"],
        )
        custom_group = 0 if signature in custom_article_signatures else 1
        return (custom_group, source_priority(article["source"]))

    def is_higher_priority(article: MediaItem, existing: MediaItem) -> bool:
        return dedupe_priority(article) < dedupe_priority(existing)

    article_by_url: dict[str, MediaItem] = {}
    article_by_title: dict[str, MediaItem] = {}

    def add_article(article: MediaItem) -> None:
        url = normalize_url(article["url"])
        if url:
            article_by_url[url] = article
        article_by_title[normalize_title(article["title"])] = article

    def remove_article(article: MediaItem) -> None:
        url = normalize_url(article["url"])
        if url:
            article_by_url.pop(url, None)
        article_by_title.pop(normalize_title(article["title"]), None)

    for article in all_articles:
        url = article["url"].strip()
        if url_is_excluded_own_site(url):
            continue
        url_key = normalize_url(url)
        title_key = normalize_title(article["title"])
        url_existing = article_by_url.get(url_key) if url_key else None
        title_existing = article_by_title.get(title_key)
        conflicts = {
            id(existing): existing
            for existing in (url_existing, title_existing)
            if existing is not None
        }

        if not conflicts:
            add_article(article)
            continue

        if title_existing is not None and not is_higher_priority(article, title_existing):
            if (
                url_existing is not None
                and url_existing is not title_existing
                and is_higher_priority(article, url_existing)
            ):
                remove_article(url_existing)
            continue

        if url_existing is not None and not is_higher_priority(article, url_existing):
            continue

        for existing in conflicts.values():
            remove_article(existing)
        add_article(article)
    unique_articles = list(article_by_title.values())

    # Sort by source priority (lower first), then by date (newest first)
    def sort_key(a: MediaItem) -> tuple:
        pri = source_priority(a["source"])
        try:
            ts = -datetime.fromisoformat(a["date"].replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            ts = 0
        return (pri, ts)

    unique_articles.sort(key=sort_key)
    if existing_urls:
        existing = {u.strip() for u in existing_urls if isinstance(u, str) and u.strip()}
        if existing:
            unique_articles = [
                article
                for article in unique_articles
                if (article.get("url") or "").strip() not in existing
            ]
    return unique_articles


def get_news_data(
    scholar_name: str, existing_urls: set[str] | None = None
) -> dict[str, list[MediaItem]]:
    """Function to fetch all RSS data for a scholar that can be used by main.py"""
    articles = fetch_all_news(existing_urls=existing_urls)
    return {"media": articles}


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
