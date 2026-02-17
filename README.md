# Scholar API

This project uses a home server cronjob to scrape [Google Scholar](https://scholar.google.com.au/) data via the [scholarly](https://github.com/scholarly-python-package/scholarly) Python package and the Google Sheets to get the journal's impact factor (IF) and the publication's [DOI](https://doi.org/).

The JSON can then be used, for example, by uploading the data to a publicly accessible server via Secure Copy (SCP) or rsync, which serves the JSON data via a Flask application.

[Meltwater](https://www.meltwater.com/) is the news gathering tool used by some universities. See also Isentia Medaiportal.
See also [Zotera](https://www.zotero.org/), an [open source citation manager](https://github.com/zotero/zotero).

altmetrics

`python -m venv scholar && source scholar/bin/activate`

## Installation

### Prerequisites

- Python 3.6+
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

- **hero** – [Ulixee Hero](https://github.com/ulixee/hero) Cloud (browser automation for scraping)
- **hero-scraper** – HTTP API wrapper that sends URLs to Hero and returns HTML
- **web** – Flask API serving scholar data
- **cron** – Runs the main scraper on a schedule

Build the base image (required once; no container is created):

```bash
docker compose build base
```

Start all services (hero, hero-scraper, web, cron; base is build-only and does not run):

```bash
docker compose up -d
```

For browser-based scraping (DOIs, etc.), the hero-scraper service must be running. Set `HERO_SCRAPER_URL` (default: `http://hero-scraper:3000` in Docker, `http://localhost:3000` locally) to point at it.

### Caching

HTTP responses are cached with [requests-cache](https://requests-cache.readthedocs.io/) in `cache/` (SQLite). This includes:

- Scholarly (Google Scholar) requests
- DOI API requests (doi.org, shortdoi.org)
- Hero scraper (browser-fetched HTML)
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

Tests marked `integration` require network access. Tests that need `google-credentials.json` or the Hero scraper will skip when unavailable. Run lint and format before committing:

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
docker compose up web -d
```

The API is available at `http://localhost:8000` (Docker maps 8000→5000).

### API Endpoints

| URL | Method | Description |
|-----|--------|-------------|
| `/` | GET | Welcome message |
| `/health` | GET | Health check |
| `/scholars` | GET | List available scholar IDs |
| `/scholar/<id>` | GET | Get scholar data by ID (e.g. `/scholar/ynWS968AAAAJ`) |

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
