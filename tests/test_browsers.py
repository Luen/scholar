"""Tests for Hero scraper API (Ulixee Hero browser)."""

import os

import pytest
import requests


@pytest.mark.integration
def test_hero_scraper_health():
    """Test that the Hero scraper API health endpoint is reachable."""
    url = os.environ.get("HERO_SCRAPER_URL", "http://localhost:3000")
    if not url:
        pytest.skip("HERO_SCRAPER_URL not set")

    try:
        resp = requests.get(f"{url.rstrip('/')}/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "hero-scraper"
    except requests.RequestException as e:
        pytest.skip(f"Hero scraper not reachable: {e}")
