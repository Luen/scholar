import hashlib
import json
import logging
import os
import re
from datetime import datetime
from email.utils import formatdate

from flask import Flask, jsonify, make_response, request, send_from_directory

import src.cache_config  # noqa: F401 - configure HTTP cache before requests

from .doi_utils import normalize_doi
from .scholar_citations import (
    fetch_altmetric_score,
    fetch_google_scholar_citations,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False  # Preserve key order: doi first, then citations/score

SCHOLAR_DATA_DIR = os.environ.get("SCHOLAR_DATA_DIR", "scholar_data")
SCHOLAR_DATA_DIR_ABS = os.path.abspath(SCHOLAR_DATA_DIR)

# HTTP cache: clients revalidate after 1 day to pick up citation/score updates
DOI_CACHE_MAX_AGE = 86400  # 1 day


def _scholar_file_path(scholar_id: str) -> str | None:
    """Return safe path to scholar JSON file, or None if invalid."""
    if len(scholar_id) != 12 or not re.match(r"^[a-zA-Z0-9_-]+$", scholar_id):
        return None
    path = os.path.join(SCHOLAR_DATA_DIR_ABS, f"{scholar_id}.json")
    # Ensure path stays inside SCHOLAR_DATA_DIR (path traversal safety)
    try:
        real_path = os.path.realpath(path)
        if os.path.commonpath([real_path, SCHOLAR_DATA_DIR_ABS]) != SCHOLAR_DATA_DIR_ABS:
            return None
    except (ValueError, OSError):
        return None
    return real_path


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    """Serve favicon if present in project root."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    favicon_path = os.path.join(root, "favicon.ico")
    if os.path.isfile(favicon_path):
        return send_from_directory(root, "favicon.ico")
    return "", 204  # No content


@app.route("/", methods=["GET"])
def index():
    return "Welcome to the scholar API"


@app.route("/scholars", methods=["GET"])
def list_scholars():
    """List available scholar IDs with JSON data."""
    if not os.path.isdir(SCHOLAR_DATA_DIR_ABS):
        return jsonify({"scholars": []}), 200
    try:
        ids = [
            f.replace(".json", "") for f in os.listdir(SCHOLAR_DATA_DIR_ABS) if f.endswith(".json")
        ]
        return jsonify({"scholars": sorted(ids)}), 200
    except OSError:
        return jsonify({"error": "Could not list scholars"}), 500


@app.route("/scholar/<id>", methods=["GET"])
def get_scholar(id):
    """Get scholar data by ID."""
    if not id:
        return jsonify({"error": "Missing id"}), 400
    filepath = _scholar_file_path(id)
    if not filepath:
        return jsonify({"error": "Invalid id"}), 400
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "Author not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid scholar data"}), 500


# Basic DOI pattern: prefix 10. (registry) / suffix (no strict length)
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+$")


def _normalize_doi_for_api(doi: str) -> str:
    """Normalize DOI: unquote (handles single and multiple URL-encoding) and strip."""
    return normalize_doi(doi)


def _doi_cache_headers(last_fetch: str, doi: str) -> dict[str, str]:
    """Return Cache-Control, Last-Modified, and ETag for DOI responses (1-day client cache)."""
    try:
        dt = datetime.fromisoformat(last_fetch.replace("Z", "+00:00"))
        last_modified = formatdate(dt.timestamp(), usegmt=True)
    except (ValueError, TypeError):
        last_modified = formatdate(None, usegmt=True)
    etag = hashlib.sha256(f"{doi}:{last_fetch}".encode()).hexdigest()
    return {
        "Cache-Control": f"public, max-age={DOI_CACHE_MAX_AGE}, must-revalidate",
        "Last-Modified": last_modified,
        "ETag": f'"{etag}"',
    }


def _etag_matches_request(etag: str, request_etag: str | None) -> bool:
    """True if request's If-None-Match matches our ETag (allows 304)."""
    if not request_etag:
        return False
    # If-None-Match can be "etag1", "etag1", "etag2" or *
    if request_etag.strip() == "*":
        return True
    return etag.strip() in [e.strip().strip('"') for e in request_etag.split(",")]


def _validate_doi_for_api(doi: str) -> tuple[str | None, str | None]:
    """
    Normalize and validate DOI for API use.
    Returns (normalized_doi, None) if valid, or (None, error_message) if invalid.
    """
    normalized = _normalize_doi_for_api(doi)
    if not normalized:
        return None, "Invalid DOI: empty"
    if "/" not in normalized:
        return None, "Invalid DOI: must contain a slash (e.g. 10.1234/example)"
    if "%" in normalized:
        return None, "Invalid DOI: malformed encoding (use 10.xxxx/suffix or single-encoded path)"
    if not _DOI_PATTERN.match(normalized):
        return None, "Invalid DOI: must match 10.xxxx/suffix format"
    return normalized, None


@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    """Serve robots.txt to avoid 404s from crawlers and reduce noisy log traffic."""
    return "User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/altmetric/<path:doi>", methods=["GET"])
def get_altmetric(doi: str):
    """
    Fetch Altmetric data for a DOI. Cached for 2 weeks.
    Returns full Altmetric data (score, title, authors, counts, etc.).
    Returns 401 if Crossref does not list Rummer, Bergseth, or Wu.
    Query param ?refresh=1 (dev only) forces a fresh fetch.
    """
    normalized_doi, err = _validate_doi_for_api(doi)
    if err:
        resp = jsonify({"error": err})
        resp.headers["Cache-Control"] = "no-store"
        return resp, 400
    doi = normalized_doi
    force_refresh = request.args.get("refresh") == "1"  # dev only
    result = fetch_altmetric_score(doi, force_refresh=force_refresh)
    if not result.found:
        logger.warning(
            "Altmetric API returning 401 for DOI %s (publication not found or author not in allowlist)",
            doi,
        )
        body = {"error": "Publication not found or author not in allowlist"}
        if result.error_reason:
            body["reason"] = result.error_reason
        resp = jsonify(body)
        resp.headers["Cache-Control"] = "no-store"
        return resp, 401
    headers = _doi_cache_headers(result.last_fetch, result.doi)
    etag = hashlib.sha256(f"{result.doi}:{result.last_fetch}".encode()).hexdigest()
    if _etag_matches_request(etag, request.headers.get("If-None-Match")):
        resp = make_response("", 304)
        resp.headers.update(headers)
        return resp
    data = result.details if result.details else {"doi": result.doi, "score": result.score}
    data = {**data, "last_fetch": result.last_fetch}
    resp = jsonify(data)
    resp.headers.update(headers)
    return resp


@app.route("/google-citations/<path:doi>", methods=["GET"])
def get_google_citations(doi: str):
    """
    Fetch Google Scholar citation count for a DOI. Cached for 2 weeks.
    Returns 401 if Crossref does not list Rummer, Bergseth, or Wu.
    Query param ?refresh=1 (dev only) forces a fresh fetch.
    """
    normalized_doi, err = _validate_doi_for_api(doi)
    if err:
        resp = jsonify({"error": err})
        resp.headers["Cache-Control"] = "no-store"
        return resp, 400
    doi = normalized_doi
    force_refresh = request.args.get("refresh") == "1"  # dev only
    result = fetch_google_scholar_citations(doi, force_refresh=force_refresh)
    if not result.found:
        logger.warning(
            "Google citations API returning 401 for DOI %s (publication not found or author not in allowlist)",
            doi,
        )
        body = {"error": "Publication not found or author not in allowlist"}
        if result.error_reason:
            body["reason"] = result.error_reason
        resp = jsonify(body)
        resp.headers["Cache-Control"] = "no-store"
        return resp, 401
    headers = _doi_cache_headers(result.last_fetch, result.doi)
    etag = hashlib.sha256(f"{result.doi}:{result.last_fetch}".encode()).hexdigest()
    if _etag_matches_request(etag, request.headers.get("If-None-Match")):
        resp = make_response("", 304)
        resp.headers.update(headers)
        return resp
    data = {
        "doi": result.doi,
        "citations": result.citations,
        "last_fetch": result.last_fetch,
    }
    if result.warning:
        data["warning"] = result.warning
    resp = jsonify(data)
    resp.headers.update(headers)
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
