"""Finds postings whose job page is gone, so they drop off the page.

Postings from Greenhouse, Lever, Ashby and Workday already close when the company's board stops listing
them. Postings known only from the community lists, YC or Hacker News link to all kinds of career sites,
and the lists can keep a closed job for days. For those, the radar opens the link itself.

Only clear signs count as dead: a 404 or 410, or a redirect to the site's home page or an error page.
Pages saying "no longer available" don't count, because many career sites ship that text in every
page's code. A link has to look dead on two scans in a row before the posting is hidden, so one bad
moment on a company's site doesn't remove a real job. Blocked (403), slow or broken (5xx) sites are
left alone.
"""
from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .http import USER_AGENT

CHECKS_PER_SCAN = 400   # links opened per scan, least recently checked first
DEAD_AFTER = 2          # scans in a row a link must look dead before it's hidden
API_SOURCES = ("greenhouse:", "lever:", "ashby:", "workday:")


def needs_check(r: dict) -> bool:
    """Open postings that no company board API vouches for."""
    if r.get("closed") or r.get("dead_link") or not r.get("url"):
        return False
    return not any(s.startswith(API_SOURCES) for s in r.get("seen_by", {}))


def link_status(url: str, timeout: float = 15) -> str:
    """'dead', 'ok' or 'unknown'."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final = resp.geturl()
    except urllib.error.HTTPError as e:
        return "dead" if e.code in (404, 410) else "unknown"
    except Exception:
        return "unknown"
    return "dead" if _sent_away(url, final) else "ok"


def _sent_away(start: str, final: str) -> bool:
    """Redirected from a job page to the site's home page or an error page."""
    a, b = urllib.parse.urlparse(start), urllib.parse.urlparse(final)
    if "error=true" in b.query:  # Greenhouse sends closed jobs to "?error=true"
        return True
    went_somewhere_else = (a.netloc, a.path.rstrip("/")) != (b.netloc, b.path.rstrip("/"))
    return went_somewhere_else and b.path.strip("/") == "" and a.path.strip("/") != ""


def check_links(records: dict[str, dict], run_ts: str, workers: int = 16,
                budget: int = CHECKS_PER_SCAN, status_fn=link_status) -> dict:
    todo = sorted((k for k, r in records.items() if needs_check(r)),
                  key=lambda k: records[k].get("link_checked", ""))[:budget]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda k: (k, status_fn(records[k]["url"])), todo))
    counts = {"checked": len(todo), "dead": 0, "alive": 0, "unknown": 0, "hidden": 0}
    for k, status in results:
        r = records[k]
        r["link_checked"] = run_ts
        counts["alive" if status == "ok" else status] += 1
        if status == "dead":
            r["link_fails"] = r.get("link_fails", 0) + 1
            if r["link_fails"] >= DEAD_AFTER:
                r["dead_link"] = True
                counts["hidden"] += 1
        elif status == "ok":
            r.pop("link_fails", None)
    counts["ok"] = True
    counts["note"] = (f"{counts['checked']} links opened: {counts['alive']} working, {counts['dead']} look dead, "
                      f"{counts['unknown']} couldn't tell; {counts['hidden']} hidden after failing twice")
    return counts
