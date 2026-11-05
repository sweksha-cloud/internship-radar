"""Tiny HTTP helpers built on the standard library (no dependencies)."""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request

USER_AGENT = "internship-radar/1.0 (personal job alert tool; low request rate)"


class FetchError(Exception):
    pass


def fetch(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None,
          timeout: float = 20, retries: int = 2) -> tuple[int, bytes, dict]:
    """Returns (status, body_bytes, response_headers). 304 is returned, not raised."""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Encoding": "gzip"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return resp.status, raw, dict(resp.headers)
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return 304, b"", dict(e.headers)
            # 4xx (other than 429) won't get better on retry
            if e.code != 429 and e.code < 500:
                raise FetchError(f"HTTP {e.code}") from e
            last_err = FetchError(f"HTTP {e.code}")
            if e.code == 429 and attempt < retries:
                # rate limited: wait as long as the server asks (capped), then try again
                try:
                    wait = float(e.headers.get("Retry-After") or 0)
                except ValueError:
                    wait = 0
                time.sleep(min(max(wait, 5.0 * (attempt + 1)), 30))
                continue
        except Exception as e:  # timeouts, DNS, connection resets
            last_err = FetchError(type(e).__name__ + ": " + str(e)[:120])
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    raise last_err or FetchError("unknown error")


def fetch_json(url: str, **kw):
    status, raw, _ = fetch(url, **kw)
    try:
        return json.loads(raw)
    except ValueError as e:
        raise FetchError("response was not JSON") from e
