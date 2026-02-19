"""
SOCKS5 proxy configuration for outgoing requests (Altmetric, Google Scholar).

Reads SOCKS5_PROXIES from environment. Format: one proxy per line (or semicolon-
separated). Each entry: host:port|username|password (password may contain |).
Example:
  SOCKS5_PROXIES="host1:1080|user1|pass1
  host2:1080|user2|pass2"
"""

import itertools
import os
from urllib.parse import quote

_SOCKS5_PROXIES_RAW = os.environ.get("SOCKS5_PROXIES", "").strip()
_parsed_proxy_list: list[dict[str, str]] | None = None
_proxy_cycle: itertools.cycle | None = None


def _parse_socks5_proxies() -> list[dict[str, str]]:
    """Parse SOCKS5_PROXIES into a list of requests-style proxy dicts."""
    if not _SOCKS5_PROXIES_RAW:
        return []
    entries: list[str] = []
    for part in _SOCKS5_PROXIES_RAW.replace(";", "\n").splitlines():
        part = part.strip()
        if part:
            entries.append(part)
    result: list[dict[str, str]] = []
    for entry in entries:
        parts = entry.split("|", 2)
        if len(parts) < 3:
            continue
        host_port = parts[0].strip()
        user = parts[1].strip()
        password = parts[2].strip()
        if not host_port:
            continue
        # URL-encode user/password so special chars (e.g. * @) are safe in URL
        user_enc = quote(user, safe="")
        pass_enc = quote(password, safe="")
        url = f"socks5://{user_enc}:{pass_enc}@{host_port}"
        result.append({"http": url, "https": url})
    return result


def get_socks5_proxies() -> dict[str, str] | None:
    """
    Return the next SOCKS5 proxy dict for use with requests (round-robin).
    Format: {"http": "socks5://user:pass@host:port", "https": "socks5://..."}.
    Returns None if SOCKS5_PROXIES is not set or empty.
    """
    global _parsed_proxy_list, _proxy_cycle
    if _parsed_proxy_list is None:
        _parsed_proxy_list = _parse_socks5_proxies()
        if not _parsed_proxy_list:
            return None
        _proxy_cycle = itertools.cycle(_parsed_proxy_list)
    return next(_proxy_cycle)
