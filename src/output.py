"""Author data loading, saving, and schema management."""

import json
import logging
import os
from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1
logger = logging.getLogger(__name__)


def load_author(path: str) -> dict[str, Any] | None:
    """Load author data from JSON file. Returns None if file does not exist or is invalid."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load author data from %s: %s", path, e)
        return None


def save_author(author: dict[str, Any], path: str) -> None:
    """Save author data to JSON with schema_version and last_fetched."""
    author["schema_version"] = SCHEMA_VERSION
    author["last_fetched"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(author, f, indent=4)
    logger.debug("Saved author data to %s", path)


def is_fresh(last_fetched: str | None, fresh_seconds: int) -> bool:
    """Return True if last_fetched is within fresh_seconds of now."""
    if not last_fetched:
        return False
    try:
        dt = datetime.fromisoformat(last_fetched.replace("Z", "+00:00"))
        # Handle naive datetime (local time)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        age = (datetime.now(dt.tzinfo) - dt).total_seconds()
        return 0 <= age <= fresh_seconds
    except (ValueError, TypeError):
        return False


def get_last_successful_indices(data: dict[str, Any]) -> dict[str, int]:
    """Extract last successful indices for resume support."""
    return {
        "coauthor": data.get("_last_successful_coauthor_index", -1),
        "publication": data.get("_last_successful_publication_index", -1),
    }


def set_last_successful_index(author: dict[str, Any], phase: str, index: int) -> None:
    """Store last successful index for resume support."""
    key = f"_last_successful_{phase}_index"
    author[key] = index
