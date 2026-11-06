"""YC company directory, used to label postings from YC-backed startups.

Data: the open yc-oss/api dataset on GitHub (a daily mirror of ycombinator.com/companies).
Only downloaded again when it has changed.
"""
from __future__ import annotations

import json
import re

from ..http import fetch

URL = "https://raw.githubusercontent.com/yc-oss/api/main/companies/all.json"
SEASON_CODE = {"winter": "W", "summer": "S", "fall": "F", "spring": "X"}


def norm_name(name: str) -> str:
    n = (name or "").lower()
    n = re.sub(r"\(.*?\)", " ", n)
    n = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|labs?|hq|ai)\b\.?", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def short_batch(batch: str | None) -> str:
    """'Winter 2024' -> 'W24'; anything unexpected is returned as-is."""
    m = re.match(r"(winter|summer|fall|spring)\s+(\d{4})", (batch or "").strip(), re.I)
    return f"{SEASON_CODE[m.group(1).lower()]}{m.group(2)[2:]}" if m else (batch or "")


def fetch_directory(etag: str | None) -> tuple[dict | None, str | None]:
    """Returns ({normalized name or slug: info}, etag), or (None, etag) if unchanged."""
    status, raw, hdrs = fetch(URL, headers={"If-None-Match": etag} if etag else {}, timeout=90)
    new_etag = hdrs.get("ETag") or hdrs.get("Etag") or etag
    if status == 304:
        return None, new_etag
    return build_index(json.loads(raw)), new_etag


def build_index(companies: list[dict]) -> dict:
    index: dict[str, dict] = {}
    for c in companies:
        if (c.get("status") or "").lower() == "inactive":
            continue
        site = re.sub(r"^https?://(www\.)?", "", (c.get("website") or "").lower()).split("/")[0].split(".")[0]
        info = {"n": c.get("name"), "b": short_batch(c.get("batch")), "t": c.get("team_size"),
                "u": c.get("url"), "ids": sorted({_slug(c.get("slug")), _slug(site)} - {""})}
        # current name only: former names cause false matches (e.g. a startup once called "Meta")
        k = norm_name(c.get("name", ""))
        if len(k) >= 3:
            if k in index and index[k].get("n") != info["n"]:
                index[k] = {"ambiguous": True}   # two YC companies share this name: don't guess
            else:
                index.setdefault(k, info)
    return index


def _slug(x: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (x or "").lower())


def lookup(index: dict, company: str, board: str | None = None, url: str | None = None) -> dict | None:
    """Find a posting's company in the YC directory.

    Names alone can collide (a big company and a tiny YC startup both called "Voyager"), so:
    - YC companies with 500+ people match on name alone (well known, rarely confused);
    - otherwise the posting's job board must be the startup's own (board name = its YC slug or website),
      with no job board to compare, it isn't labeled (better unlabeled than wrong).
    """
    if not index:
        return None
    hit = index.get(norm_name(company))
    if not hit or hit.get("ambiguous"):
        return None
    if (hit.get("t") or 0) >= 500:
        return hit
    if not board and url:
        from ..model import parse_board
        b = parse_board(url)
        board = f"{b[0]}:{b[1]}" if b else None
    if board and ":" in board:
        if board.startswith("workday:"):
            return None  # startups almost never use Workday
        return hit if _slug(board.split(":", 1)[1]) in hit.get("ids", []) else None
    return None  # no job board to confirm it's the same company: don't label it


# ---- finding hiring YC startups' job boards ---------------------------------------------

HIRING_URL = "https://raw.githubusercontent.com/yc-oss/api/main/companies/hiring.json"
US_REGIONS = {"United States of America", "United States", "America / Canada", "Remote"}


def fetch_hiring(etag: str | None) -> tuple[list[dict] | None, str | None]:
    """Hiring YC companies in the US (or remote): [{n, s, w, b, t, u}], or (None, etag) if unchanged."""
    status, raw, hdrs = fetch(HIRING_URL, headers={"If-None-Match": etag} if etag else {}, timeout=90)
    new_etag = hdrs.get("ETag") or hdrs.get("Etag") or etag
    if status == 304:
        return None, new_etag
    out = []
    for c in json.loads(raw):
        if (c.get("status") or "").lower() == "inactive":
            continue
        if not (set(c.get("regions") or []) & US_REGIONS):
            continue
        site = re.sub(r"^https?://(www\.)?", "", (c.get("website") or "").lower()).split("/")[0].split(".")[0]
        out.append({"n": c.get("name"), "s": c.get("slug") or "", "w": site,
                    "b": short_batch(c.get("batch")), "t": c.get("team_size"), "u": c.get("url")})
    return out, new_etag


def board_candidates(c: dict) -> list[str]:
    """Likely job-board names for a YC company, most likely first (YC slug, website name, company name)."""
    raw = [c.get("s", ""), (c.get("s") or "").replace("-", ""), c.get("w", ""), _slug(c.get("n"))]
    seen, out = set(), []
    for x in raw:
        x = (x or "").strip().lower()
        if len(x) >= 2 and x not in seen:
            seen.add(x)
            out.append(x)
    return out[:3]


def probe_company(c: dict, fetchers: dict) -> tuple[list[str], int]:
    """Try each candidate name on Ashby, Greenhouse and Lever. Returns (boards with open jobs, requests made).
    A board only counts if it has at least one open job, so empty or unrelated names are ignored."""
    found, requests = [], 0
    for system in ("ashby", "greenhouse", "lever"):
        for cand in board_candidates(c):
            requests += 1
            try:
                if fetchers[system](cand, retries=0):   # one quick try: most guesses don't exist
                    found.append(f"{system}:{cand}")
                    break
            except Exception:
                continue
    return found, requests
