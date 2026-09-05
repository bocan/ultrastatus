"""One HTTP helper. Provider tests monkeypatch fetch_bytes."""

import urllib.request

USER_AGENT = "statusboard/0.1 (+https://github.com/cloudcauldron/statusboard)"


def fetch_bytes(url: str, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        if status < 200 or status >= 300:
            raise RuntimeError(f"GET {url} returned HTTP {status}")
        return response.read()
