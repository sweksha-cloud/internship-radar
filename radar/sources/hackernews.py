"""Hacker News "Ask HN: Who is hiring?" (official API: https://github.com/HackerNews/API).

Each month YC's account 'whoishiring' posts a thread; every top-level comment is one company.
Only comments we haven't read before are fetched, so later scans are cheap.
"""
from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor

from ..http import fetch_json
from ..model import Posting, ts_to_iso

API = "https://hacker-news.firebaseio.com/v0"
INTERN_RE = re.compile(r"(?<![a-z])(intern|interns|internship|internships|co-?op)(?![a-z])", re.I)


def latest_thread_id() -> int | None:
    user = fetch_json(f"{API}/user/whoishiring.json")
    for sid in (user.get("submitted") or [])[:12]:
        item = fetch_json(f"{API}/item/{sid}.json") or {}
        if (item.get("title") or "").lower().startswith("ask hn: who is hiring"):
            return sid
    return None


def fetch_new_comments(thread_id: int, seen_ids: set[int]) -> tuple[list[Posting], list[int]]:
    thread = fetch_json(f"{API}/item/{thread_id}.json") or {}
    kids = [k for k in (thread.get("kids") or []) if k not in seen_ids]

    def get(cid):
        try:
            return fetch_json(f"{API}/item/{cid}.json", retries=1)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=16) as ex:
        comments = list(ex.map(get, kids))
    postings = []
    read_ids = []
    for c in comments:
        if not c:
            continue
        read_ids.append(c["id"])
        p = parse_comment(c)
        if p:
            postings.append(p)
    return postings, read_ids


def parse_comment(c: dict) -> Posting | None:
    if c.get("deleted") or c.get("dead") or not c.get("text"):
        return None
    text = html.unescape(re.sub(r"<[^>]+>", "\n", c["text"]))
    if not INTERN_RE.search(text):
        return None
    first = text.strip().split("\n", 1)[0].strip()
    fields = [f.strip() for f in first.split("|") if f.strip()]
    company = fields[0] if fields else "HN company"
    # the role field is usually the one that mentions intern/engineer
    role = next((f for f in fields[1:] if INTERN_RE.search(f)), None) or "Internship (see post)"
    title = role if INTERN_RE.search(role) else f"{role} (mentions internships)"
    loc_fields = [f for f in fields[1:] if re.search(
        r"remote|onsite|on-site|hybrid|,\s*[A-Z]{2}\b|usa|united states|\bUS\b|new york|san francisco|sf\b|nyc|seattle|boston|austin",
        f, re.I)]
    return Posting(
        company=company[:80],
        title=title[:140],
        url=f"https://news.ycombinator.com/item?id={c['id']}",
        source="hackernews",
        locations=loc_fields[:3],
        remote=True if re.search(r"remote", first, re.I) else None,
        posted_at=ts_to_iso(c.get("time")),
    )
