"""One HTTP helper. Provider tests monkeypatch fetch_bytes."""

import os
import socket
import urllib.request

USER_AGENT = "statusboard/0.1 (+https://github.com/bocan/ultrastatus)"

_original_getaddrinfo = socket.getaddrinfo


def ipv4_first(results: list) -> list:
    """Keep only IPv4 entries when there are any. A v6-only host keeps its v6 entries."""
    v4 = [r for r in results if r[0] == socket.AF_INET]
    return v4 or results


def _getaddrinfo_ipv4_first(*args, **kwargs):
    return ipv4_first(_original_getaddrinfo(*args, **kwargs))


def prefer_ipv4(enabled: bool = True) -> None:
    """Route every DNS lookup in this process through an IPv4-first filter.

    On a box where IPv6 is configured but not routed, each connection waits
    the full timeout on the v6 address before falling back. Twenty fetches a
    poll turns that into minutes. Set STATUSBOARD_IPV6=1 to leave lookups alone.
    """
    socket.getaddrinfo = _getaddrinfo_ipv4_first if enabled else _original_getaddrinfo


def prefer_ipv4_from_env() -> None:
    prefer_ipv4(os.environ.get("STATUSBOARD_IPV6") != "1")


def fetch_bytes(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        if status < 200 or status >= 300:
            raise RuntimeError(f"GET {url} returned HTTP {status}")
        return response.read()
