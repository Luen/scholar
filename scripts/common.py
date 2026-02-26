"""
Shared setup and data for scripts in this folder.

Use setup_script() at the start of each script so project root is on sys.path
and cache/proxy config (including TOR_PROXY from .env) is loaded.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def setup_script() -> None:
    """Add script dir and project root to sys.path; load cache/proxy config (e.g. TOR_PROXY)."""
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    import src.cache_config  # noqa: E402, F401


# Single source of truth for test DOI list (Crossref allowlist check, metrics tests)
DOIS = [
    "10.1242/jeb.151738",
    "10.1242/jeb.113803",
    "10.1242/jeb.192245",
    "10.7717/peerj.20222",
    "10.1016/j.tree.2023.12.004",
    "10.1111/cobi.14390",
    "10.1655/0018-0831-77.1.37",
    "10.1093/conphys/coaa138",
    "10.7717/peerj.3805",
    "10.1098/rsif.2018.0276",
    "10.5268/IW-3.3.550",
    "10.1111/gcb.15127",
    "10.1038/s41598-022-09950-y",
    "10.1093/conphys/coaf038",
    "10.1038/s41586-025-08665-0",
    "10.1111/geb.13602",
    "10.1242/jeb.210732",
    "10.1111/geb.13502",
    "10.1038/s41598-018-22002-8",
    "10.2744/CCB-1185.1",
    "10.1242/jeb.243295",
    "10.1242/jeb.191817",
    "10.1016/j.cbpa.2024.111688",
]
