"""YC jobs board (https://www.ycombinator.com/jobs).

There is no official API, so this reads the public pages. It tries the page's embedded
JSON data first and falls back to reading job links. If YC changes the page, this source
shows an error on the radar page instead of silently returning nothing.
"""
from __future__ import annotations

import html
import json
import re

from ..http import fetch, FetchError
from ..model import Posting

PAGES = [
    "https://www.ycombinator.com/jobs/role/software-engineer",
    "https://www.ycombinator.com/jobs",
]
JOB_PATH = re.compile(r"/companies/([a-z0-9-]+)/jobs/([A-Za-z0-9-]+)")


def fetch_yc() -> list[Posting]:
    found: dict[str, Posting] = {}
    errors = []
    for url in PAGES:
        try:
            _, raw, _ = fetch(url, headers={"Accept": "text/html"})
        except FetchError as e:
            errors.append(f"{url}: {e}")
            continue
        for p in parse_yc_html(raw.decode("utf-8", "replace")):
            found.setdefault(p.url, p)
    if not found and errors:
        raise FetchError("; ".join(errors))
    if not found:
        raise FetchError("page loaded but no jobs could be read (YC may have changed its page)")
    return list(found.values())


def parse_yc_html(page: str) -> list[Posting]:
    out: list[Posting] = []
    # 1) embedded JSON (Inertia-style data-page attribute or JSON script tags)
    blobs = re.findall(r'data-page="([^"]+)"', page)
    blobs += re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S)
    for blob in blobs:
        try:
            data = json.loads(html.unescape(blob))
        except ValueError:
            continue
        for job in _walk_jobs(data):
            out.append(job)
    if out:
        return out
    # 2) plain links: <a href="/companies/acme/jobs/abc-software-engineer-intern">Title</a>
    for m in re.finditer(r'<a[^>]+href="(/companies/[a-z0-9-]+/jobs/[^"]+)"[^>]*>(.*?)</a>', page, re.S):
        path, inner = m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))
        title = " ".join(html.unescape(inner).split())
        jm = JOB_PATH.search(path)
        if not jm or not title:
            continue
        out.append(Posting(company=jm.group(1).replace("-", " ").title(), title=title,
                           url="https://www.ycombinator.com" + path, source="yc"))
    return out


def _walk_jobs(node):
    if isinstance(node, dict):
        title = node.get("title") or node.get("name")
        url = node.get("url") or node.get("jobUrl") or node.get("path") or ""
        company = node.get("companyName") or node.get("company_name") or (
            node.get("company", {}).get("name") if isinstance(node.get("company"), dict) else None)
        slug = node.get("companySlug") or node.get("company_slug")
        if title and isinstance(title, str) and (company or slug) and (url or node.get("id")):
            if not url and slug and node.get("id"):
                url = f"/companies/{slug}/jobs/{node['id']}"
            if url.startswith("/"):
                url = "https://www.ycombinator.com" + url
            loc = node.get("location") or node.get("locations") or []
            yield Posting(
                company=company or slug.replace("-", " ").title(),
                title=title,
                url=url,
                source="yc",
                locations=loc if isinstance(loc, list) else [str(loc)],
                remote=True if node.get("remote") in (True, "yes", "only") else None,
            )
            return
        for v in node.values():
            yield from _walk_jobs(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_jobs(v)
