"""Structured logging configuration for the scholar scraper."""

import json
import logging
import os
import sys
from datetime import datetime


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for machine parsing (e.g. in Docker)."""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log)


def setup_logging(
    level: str | int = "INFO",
    json_format: bool | None = None,
) -> None:
    """Configure root logger with console and optional JSON format."""
    if json_format is None:
        json_format = os.environ.get("LOG_FORMAT", "text").lower() == "json"

    root = logging.getLogger()
    root.setLevel(level if isinstance(level, int) else getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(root.level)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )
    root.handlers.clear()
    root.addHandler(handler)
