# Scholar API

This project uses a home server cronjob to scrape [Google Scholar](https://scholar.google.com.au/) data via the [scholarly](https://github.com/scholarly-python-package/scholarly) Python package and the Google Sheets to get the journal's impact factor (IF) and the publication's [DOI](https://doi.org/).

The JSON can then be used, for example, by uploading the data to a publicly accessible server via Secure Copy (SCP) or rsync, which serves the JSON data via a Flask application.

[Meltwater](https://www.meltwater.com/) is the news gathering tool used by some universities. See also Isentia Medaiportal.
See also [Zotera](https://www.zotero.org/), an [open source citation manager](https://github.com/zotero/zotero).

`python -m venv scholar && source scholar/bin/activate`

## Installation

### Prerequisites

- Python 3.10+ (required by Scrapling)
- Flask
- scholarly
- Wikipedia

### Setup

1. Clone this repository to your local machine.
2. Install the required packages.
3. Setup.

    ```bash
    git clone https://github.com/Luen/scholarly-api
    python -m venv scholar
    source scholar/bin/activate
    pip install -r requirements.txt
    ```

4. Test run.

    ```bash
    python main.py ynWS968AAAAJ
    ```

## Docker

The stack includes:

- **web** – Flask API serving scholar data
- **cron** – Runs the main scraper and DOI metrics revalidation on a schedule

**Cron schedule** (in `cron/Dockerfile`): main scholar pipeline at 00:00 every 14 days; DOI metrics revalidation (Altmetric / Google Scholar cache) at **02:00 daily**.

Build the base image (required once; no container is created):

```bash
docker compose build base
```

Start all services (web, cron; base is build-only and does not run):

```bash
docker compose up -d
```

For browser-based DOI fetching on sites that block plain HTTP, the project uses [Scrapling](https://github.com/D4Vinci/Scrapling). Install browser dependencies with `scrapling install` if you use that path. News aggregation uses RSS, [NewsAPI](https://newsapi.org/), the Guardian API, [Newspaper4k](https://github.com/AndyTheFactory/newspaper4k), and other sources.

### Caching

HTTP responses are cached with [requests-cache](https://requests-cache.readthedocs.io/) in `cache/` (SQLite). This includes:

- Scholarly (Google Scholar) requests
- DOI API requests (doi.org, shortdoi.org)
- Scrapling (browser-fetched HTML for DOI extraction)
- Web page fetches for DOI extraction

Set `CACHE_DIR` to change the cache location; `CACHE_EXPIRE_SECONDS` (default: 30 days) to control expiry.

Wait for containers to be ready (check status with `docker compose ps`). Then to manually run the script:

```bash
# First check if containers are ready
docker compose ps

# If containers are running, execute the script
docker compose exec cron python main.py ynWS968AAAAJ

# If you get a "container is restarting" error, check logs
docker compose logs web
```

### Testing SOCKS5 proxies

If you use `SOCKS5_PROXIES` (see `.env.template`), you can test each proxy from inside the web container:

```bash
docker exec scholar_web python -c "
import os, requests
from urllib.parse import quote
raw = os.environ.get('SOCKS5_PROXIES', '').strip()
if not raw:
    print('No SOCKS5_PROXIES set'); exit(0)
for i, entry in enumerate([p.strip() for p in raw.replace(';', chr(10)).splitlines() if p.strip()]):
    parts = entry.split('|', 2)
    if len(parts) < 3:
        print(f'Proxy {i+1}: invalid format'); continue
    host_port, user, passw = parts[0].strip(), parts[1].strip(), parts[2].strip()
    url = 'socks5://' + quote(user, safe='') + ':' + quote(passw, safe='') + '@' + host_port
    try:
        r = requests.get('https://api.altmetric.com/v1/doi/10.1038/nature.2014.14950', proxies={'http': url, 'https': url}, timeout=15)
        print(f'Proxy {i+1} ({host_port}): OK')
    except Exception as e:
        print(f'Proxy {i+1} ({host_port}): FAIL - {e}')
"
```

```bash
docker exec scholar_web python -c "
import os, requests
from urllib.parse import quote
raw = os.environ.get('SOCKS5_PROXIES', '').strip()
if not raw:
    print('No SOCKS5_PROXIES set'); exit(0)
for i, entry in enumerate([p.strip() for p in raw.replace(';', chr(10)).splitlines() if p.strip()]):
    parts = entry.split('|', 2)
    if len(parts) < 3:
        print(f'Proxy {i+1}: invalid format'); continue
    host_port, user, passw = parts[0].strip(), parts[1].strip(), parts[2].strip()
    url = 'socks5://' + quote(user, safe='') + ':' + quote(passw, safe='') + '@' + host_port
    try:
        r = requests.get('https://www.altmetric.com/details/doi/10.1038/s41586-025-08665-0', proxies={'http': url, 'https': url}, timeout=30)
        print(f'Proxy {i+1} ({host_port}): OK status={r.status_code}')
    except Exception as e:
        print(f'Proxy {i+1} ({host_port}): FAIL - {e}')
"
```

Test whether each proxy is blocked by Google Scholar (CAPTCHA / "unusual traffic"). Uses the same block detection as the app:

```bash
docker exec scholar_web python -c "
import os, requests
from urllib.parse import quote
raw = os.environ.get('SOCKS5_PROXIES', '').strip()
if not raw:
    print('No SOCKS5_PROXIES set'); exit(0)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://scholar.google.com/',
}
block_signals = ('captcha', 'recaptcha', 'unusual traffic', 'automated queries', 'our systems have detected', 'sorry, we have detected')
scholar_url = 'https://scholar.google.com/scholar?hl=en&as_sdt=0%2C5&q=' + quote('10.1111/1365-2435.70147') + '&btnG='
for i, entry in enumerate([p.strip() for p in raw.replace(';', chr(10)).splitlines() if p.strip()]):
    parts = entry.split('|', 2)
    if len(parts) < 3:
        print(f'Proxy {i+1}: invalid format'); continue
    host_port, user, passw = parts[0].strip(), parts[1].strip(), parts[2].strip()
    url = 'socks5://' + quote(user, safe='') + ':' + quote(passw, safe='') + '@' + host_port
    try:
        r = requests.get(scholar_url, headers=headers, proxies={'http': url, 'https': url}, timeout=30)
        lower = r.text.lower()
        blocked = any(s in lower for s in block_signals) or 'scholar.google.com' not in (r.url or '')
        if blocked:
            print(f'Proxy {i+1} ({host_port}): BLOCKED (CAPTCHA or rate limit)')
        else:
            print(f'Proxy {i+1} ({host_port}): OK (not blocked) status={r.status_code}')
    except Exception as e:
        print(f'Proxy {i+1} ({host_port}): FAIL - {e}')
"
```

The app **does** switch to the next proxy when one fails (timeout or block). It tries **TOR_PROXY first** (up to 5 attempts), then **each SOCKS5 proxy** in order. If `TOR_PROXY` is set and Tor is slow or unreachable, each DOI request can wait up to ~2.5 minutes on Tor before SOCKS5 is tried. To use SOCKS5 only, unset `TOR_PROXY` in `.env`; or ensure Tor is responsive so the chain moves on quickly.

### Revalidating DOI metrics cache

Refreshes Altmetric and Google Scholar data. Runs daily at 02:00 in the cron container. DOIs are read from `scholar_data` (all publications with a DOI):

```bash
docker exec scholar_web python scripts/revalidate_scholar_citations.py
```

- **Phase 1 (every run):** Refetches DOIs with no cache or with a blocked/warning cache (missing or previously failed), so they are retried on each daily run.
- **Phase 2 (only after 7 days):** Revalidates DOIs that have successful cache older than a week.

Neither phase uses `force_refresh`, so if a request is blocked you keep existing cache. Run manually after fixing proxies to fill in missing DOIs.

## Project structure

- `main.py` – Orchestration only: loads config, runs pipeline, handles idempotency
- `src/scholar_fetcher.py` – Author, coauthors, publications from scholarly (with retries)
- `src/doi_resolver.py` – DOI lookup and resolution (with retries)
- `src/output.py` – Load/save JSON, `schema_version`, `last_fetched`, resume indices
- `src/config.py` – Config loaded from `.env`
- `src/retry.py` – Retry decorator with exponential backoff
- `src/logging_config.py` – Structured logging (text or JSON)

Output JSON includes `schema_version`, `last_fetched`, and `_last_successful_*_index` for resume support.

## Development

### Linting and formatting

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Run after code changes:

```bash
ruff check . --fix && ruff format .
```

### Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests marked `integration` require network access. Tests that need `google-credentials.json` or Scrapling browsers will skip when unavailable. Run lint and format before committing:

```bash
ruff check . && ruff format --check .
```

## Starting the Flask server

Navigate to the project directory and run:

```bash
python server.py
```

Or with Docker:

```bash
docker compose up web cron -d --build
docker compose down; docker volume rm scholar_cache; docker compose up web cron -d --build
```

The API is available at `http://localhost:8000` (Docker maps 8000→5000).

### API Endpoints

| URL | Method | Description |
|-----|--------|-------------|
| `/` | GET | Welcome message |
| `/health` | GET | Health check |
| `/scholars` | GET | List available scholar IDs |
| `/scholar/<id>` | GET | Get scholar data by ID (e.g. `/scholar/ynWS968AAAAJ`) |
| `/altmetric/<doi>` | GET | Altmetric score for a DOI (cached 2 weeks). 401 if not Rummer/Bergseth/Wu |
| `/scholar-citations/<doi>` | GET | Google Scholar citation count for a DOI (cached 2 weeks). 401 if not Rummer/Bergseth/Wu |

### Environment variables

- `FLASK_HOST` – Bind host (default: `0.0.0.0`)
- `FLASK_PORT` – Bind port (default: `5000`)
- `SCHOLAR_DATA_DIR` – Path to scholar JSON files (default: `scholar_data`)
- `CACHE_DIR` – HTTP cache directory (default: `cache`)
- `CACHE_EXPIRE_SECONDS` – Cache expiry (default: 30 days)
- `FRESH_DATA_SECONDS` – Skip full fetch if data is newer (default: 7 days)
- `MAX_RETRIES`, `RETRY_BASE_DELAY` – Retry settings for Scholar/DOI APIs
- `COAUTHOR_DELAY`, `PUBLICATION_DELAY` – Rate limiting (seconds)
- `LOG_FORMAT` – Set to `json` for structured JSON logs (e.g. in Docker)
- `NEWS_API_ORG_KEY`, `THE_GUARDIAN_API_KEY` – For news aggregation (see `.env.template`)
