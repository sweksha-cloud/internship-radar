"""YC jobs board (https://www.ycombinator.com/jobs) and each YC company's public jobs page.

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


# ---- each YC company's own jobs page ---------------------------------------------------
# ycombinator.com/companies/<slug>/jobs lists every role the company posts on Work at a Startup,
# no login needed. It's the only public place to see startups that have no Ashby/Greenhouse/Lever board.

def fetch_company_jobs(slug: str, company: str) -> list[Posting]:
    _, raw, _ = fetch(f"https://www.ycombinator.com/companies/{slug}/jobs", headers={"Accept": "text/html"})
    return parse_company_jobs(raw.decode("utf-8", "replace"), company)


def parse_company_jobs(page: str, company: str) -> list[Posting]:
    m = re.search(r'data-page="([^"]+)"', page)
    if not m:
        raise FetchError("no page data (YC may have changed its page)")
    jobs = json.loads(html.unescape(m.group(1))).get("props", {}).get("jobPostings")
    if jobs is None:
        raise FetchError("no jobPostings on the page (YC may have changed its page)")
    out = []
    for j in jobs:
        title = (j.get("title") or "").strip()
        if not title or not j.get("url"):
            continue
        if (j.get("type") or "").lower() != "internship" and not re.search(r"\bintern", title, re.I):
            continue
        if not re.search(r"\bintern|co-?op\b", title, re.I):
            title += " (Internship)"   # YC marks it an internship even when the title doesn't say so
        locs = [x.strip() for x in (j.get("location") or "").split(" / ") if x.strip()]
        out.append(Posting(company=j.get("companyName") or company, title=title,
                           url="https://www.ycombinator.com" + j["url"], source="yc", locations=locs,
                           remote=True if any("remote" in x.lower() for x in locs) else None))
    return out
