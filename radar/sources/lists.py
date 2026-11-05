"""Community internship lists. Used two ways:
1. as a source of postings (a backup for anything the direct checks miss), and
2. to discover which company job boards to check directly (every posting link names its board).
"""
from __future__ import annotations

import json

from ..http import fetch
from ..model import Posting, ts_to_iso, parse_board

LISTS = {
    "Simplify": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "vanshb03": "https://raw.githubusercontent.com/vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json",
}


def fetch_list(name: str, url: str, etag: str | None = None) -> tuple[list[dict] | None, str | None]:
    """Returns (items or None if unchanged, new_etag)."""
    headers = {"If-None-Match": etag} if etag else {}
    status, raw, hdrs = fetch(url, headers=headers, timeout=60)
    new_etag = hdrs.get("ETag") or hdrs.get("Etag") or etag
    if status == 304:
        return None, new_etag
    return json.loads(raw), new_etag


def to_postings(name: str, items: list[dict]) -> list[Posting]:
    out = []
    for x in items:
        if not x.get("active", True) or not x.get("is_visible", True):
            continue
        terms = x.get("terms") if isinstance(x.get("terms"), list) else x.get("season")
        from ..filters import detect_season
        out.append(Posting(
            company=x.get("company_name", ""),
            title=x.get("title", ""),
            url=x.get("url", ""),
            source=f"list:{name}",
            locations=x.get("locations") or [],
            season=detect_season(x.get("title", ""), terms),
            posted_at=ts_to_iso(x.get("date_posted")),
            category=x.get("category"),
        ))
    return out


def discover_boards(items: list[dict], max_age_days: int = 540) -> dict[str, str]:
    """board id ('greenhouse:stripe') -> company name, for companies that posted internships recently."""
    import time
    cutoff = time.time() - max_age_days * 86400
    boards: dict[str, str] = {}
    for x in items:
        if (x.get("date_posted") or 0) < cutoff:
            continue
        b = parse_board(x.get("url", ""))
        if not b:
            continue
        system, board = b
        if system == "workday" and ("private" in board.lower() or "internal" in board.lower()):
            continue
        boards.setdefault(f"{system}:{board}", x.get("company_name") or board)
    return boards
