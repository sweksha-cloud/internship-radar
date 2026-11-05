"""Direct company job boards: Greenhouse, Lever, Ashby (official public APIs) and Workday.

One connector per job system covers every company that uses it, so adding a company
is just adding its board name, never new code.
"""
from __future__ import annotations

from urllib.parse import quote

from ..http import fetch_json
from ..model import Posting, ts_to_iso


def fetch_greenhouse(board: str) -> list[Posting]:
    data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{quote(board)}/jobs")
    return parse_greenhouse(board, data)


def parse_greenhouse(board: str, data: dict) -> list[Posting]:
    out = []
    company = (data.get("meta") or {}).get("name") or board
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name") or ""
        out.append(Posting(
            company=j.get("company_name") or company,
            title=j.get("title", ""),
            url=j.get("absolute_url") or f"https://job-boards.greenhouse.io/{board}/jobs/{j.get('id')}",
            source="greenhouse",
            locations=[s.strip() for s in loc.split(";") if s.strip()] if loc else [],
            posted_at=ts_to_iso(j.get("first_published") or j.get("updated_at")),
            board=f"greenhouse:{board}",
        ))
        # absolute_url can be a company domain; keep the job id findable for de-duplication
        if "gh_jid" not in out[-1].url and "greenhouse.io" not in out[-1].url and j.get("id"):
            sep = "&" if "?" in out[-1].url else "?"
            out[-1].url += f"{sep}gh_jid={j['id']}"
    return out


def fetch_lever(board: str) -> list[Posting]:
    data = fetch_json(f"https://api.lever.co/v0/postings/{quote(board)}?mode=json")
    return parse_lever(board, data)


def parse_lever(board: str, data: list) -> list[Posting]:
    out = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        locs = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
        wtype = (j.get("workplaceType") or "").lower()
        out.append(Posting(
            company=board,
            title=j.get("text", ""),
            url=j.get("hostedUrl") or f"https://jobs.lever.co/{board}/{j.get('id')}",
            source="lever",
            locations=locs,
            remote=True if wtype == "remote" else None,
            posted_at=ts_to_iso(j.get("createdAt")),
            board=f"lever:{board}",
        ))
    return out


def fetch_ashby(board: str) -> list[Posting]:
    data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{quote(board)}")
    return parse_ashby(board, data)


def parse_ashby(board: str, data: dict) -> list[Posting]:
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [
            (s.get("location") or "") for s in (j.get("secondaryLocations") or [])]
        country = (((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or "")
        if country and country not in " ".join(locs):
            locs.append(country)
        out.append(Posting(
            company=board,
            title=j.get("title", ""),
            url=j.get("jobUrl") or f"https://jobs.ashbyhq.com/{board}/{j.get('id')}",
            source="ashby",
            locations=[l for l in locs if l],
            remote=True if (j.get("isRemote") or (j.get("workplaceType") or "").lower() == "remote") else None,
            posted_at=ts_to_iso(j.get("publishedAt")),
            board=f"ashby:{board}",
        ))
    return out


def workday_urls(board: str) -> tuple[str, str]:
    """(api_url, job_url_prefix) for 'tenant.wd5/Site' or 'site:wd5/tenant/Site'."""
    if board.startswith("site:"):
        wd, tenant, site = board[5:].split("/", 2)
        base = f"https://{wd}.myworkdaysite.com"
        return f"{base}/wday/cxs/{tenant}/{site}/jobs", f"{base}/recruiting/{tenant}/{site}"
    host_part, site = board.split("/", 1)
    tenant, wd = host_part.split(".", 1)
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    return f"{base}/wday/cxs/{tenant}/{site}/jobs", f"{base}/{site}"


def fetch_workday(board: str, search: str = "intern", pages: int = 2) -> list[Posting]:
    api, prefix = workday_urls(board)
    out: list[Posting] = []
    for page in range(pages):
        data = fetch_json(api, method="POST", body={
            "appliedFacets": {}, "limit": 20, "offset": page * 20, "searchText": search})
        batch = parse_workday(board, data, prefix)
        out.extend(batch)
        if len(batch) < 20:
            break
    return out


def parse_workday(board: str, data: dict, prefix: str) -> list[Posting]:
    company = board.split(".")[0] if not board.startswith("site:") else board.split("/")[1]
    out = []
    for j in data.get("jobPostings", []):
        path = j.get("externalPath") or ""
        out.append(Posting(
            company=company,
            title=j.get("title", ""),
            url=prefix + path,
            source="workday",
            locations=[j["locationsText"]] if j.get("locationsText") else [],
            posted_at=_workday_posted(j.get("postedOn")),
            board=f"workday:{board}",
        ))
    return out


def _workday_posted(text: str | None) -> str | None:
    """Workday says 'Posted Today', 'Posted Yesterday', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'."""
    import re
    from datetime import datetime, timedelta, timezone
    if not text:
        return None
    t = text.lower()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if "today" in t:
        days = 0
    elif "yesterday" in t:
        days = 1
    else:
        m = re.search(r"(\d+)\+?\s*day", t)
        if not m:
            return None
        days = int(m.group(1))
    return (now - timedelta(days=days)).isoformat()


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workday": fetch_workday,
}
