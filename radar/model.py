"""The shared posting shape, plus turning job URLs into stable IDs for de-duplication."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs


@dataclass
class Posting:
    company: str
    title: str
    url: str
    source: str                     # e.g. "greenhouse", "list:Simplify", "yc", "hackernews"
    locations: list[str] = field(default_factory=list)
    remote: bool | None = None
    season: str | None = None
    posted_at: str | None = None    # ISO time the company says it was posted, if known
    category: str | None = None
    board: str | None = None        # "greenhouse:stripe" etc.

    @property
    def key(self) -> str:
        return job_key(self.url) or "ct:" + company_title_key(self.company, self.title, self.locations)

    @property
    def ct_key(self) -> str:
        return company_title_key(self.company, self.title, self.locations)

    def to_dict(self) -> dict:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ts_to_iso(value) -> str | None:
    """Accepts unix seconds, unix ms, or an ISO string."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 1e11:
                v /= 1000.0
            return datetime.fromtimestamp(v, timezone.utc).replace(microsecond=0).isoformat()
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def company_title_key(company: str, title: str, locations: list[str] | None = None) -> str:
    return f"{_norm(company)}|{_norm(title)}"


_GH_PATH = re.compile(r"/([A-Za-z0-9_-]+)/jobs/(\d+)")
_WD_HOST = re.compile(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$")
_WD_SITE_HOST = re.compile(r"^(wd\d+)\.myworkdaysite\.com$")


def parse_board(url: str) -> tuple[str, str] | None:
    """Job-board identity from any posting URL: ('greenhouse', 'stripe'),
    ('workday', 'nvidia.wd5/NVIDIAExternalCareerSite'), ... or None."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    path = parts.path
    segs = [s for s in path.split("/") if s]
    qs = parse_qs(parts.query)
    if host.endswith("greenhouse.io"):
        if "for" in qs:
            return ("greenhouse", qs["for"][0].lower())
        if segs and segs[0] not in ("embed", "v1"):
            return ("greenhouse", segs[0].lower())
        return None
    if host == "jobs.lever.co" and segs:
        return ("lever", segs[0])
    if host == "jobs.ashbyhq.com" and segs:
        return ("ashby", segs[0])
    m = _WD_HOST.match(host)
    if m and segs:
        tenant, wd = m.groups()
        if re.fullmatch(r"[a-z]{2}-[a-z]{2}", segs[0], re.I):
            segs = segs[1:]
        if segs and segs[0] not in ("job", "wday"):
            return ("workday", f"{tenant}.{wd}/{segs[0]}")
        return None
    m = _WD_SITE_HOST.match(host)
    if m and "recruiting" in segs:
        i = segs.index("recruiting")
        if len(segs) > i + 2:
            return ("workday", f"site:{m.group(1)}/{segs[i + 1]}/{segs[i + 2]}")
    return None


def job_key(url: str) -> str | None:
    """A stable ID for the same job seen through different sources."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    qs = parse_qs(parts.query)
    if "gh_jid" in qs:  # Greenhouse job embedded on a company's own site
        return f"greenhouse:{qs['gh_jid'][0]}"
    if host.endswith("greenhouse.io"):
        m = re.search(r"/jobs/(\d+)", parts.path)
        if m:
            return f"greenhouse:{m.group(1)}"
        if "token" in qs:
            return f"greenhouse:{qs['token'][0]}"
    segs = [s for s in parts.path.split("/") if s]
    if host == "jobs.lever.co" and len(segs) >= 2:
        return f"lever:{segs[1].lower()}"
    if host == "jobs.ashbyhq.com" and len(segs) >= 2:
        return f"ashby:{segs[1].lower()}"
    if "myworkday" in host and segs:
        tenant = host.split(".")[0]
        if tenant.startswith("wd") and "recruiting" in segs:
            tenant = segs[segs.index("recruiting") + 1]
        last = segs[-1]
        if last.lower() in ("apply", "applymanually", "autofillwithresume"):
            last = segs[-2]
        return f"workday:{tenant}:{last.lower()}"
    if host.endswith("ycombinator.com") and "jobs" in segs:
        return "yc:" + segs[-1].lower()
    if host == "news.ycombinator.com" and "id" in qs:
        return "hn:" + qs["id"][0]
    return None
