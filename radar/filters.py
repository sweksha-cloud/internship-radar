"""Deciding which postings count: internship? right role? in the US? which season?"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    internship_keywords: list[str]
    role_keywords: list[str]
    list_categories: list[str]
    exclude_keywords: list[str]
    seasons: list[str]
    allow_remote: bool = True
    allow_unknown: bool = True
    hide_past_seasons: bool = True
    include_places: list = field(default_factory=list)
    exclude_places: list = field(default_factory=list)
    alerts_enabled: bool = True
    max_age_days: float = 3
    max_individual_alerts: int = 8
    sources: dict = field(default_factory=dict)
    always_check: list[str] = field(default_factory=list)
    skip: list[str] = field(default_factory=list)

    def source_on(self, name: str) -> bool:
        return bool(self.sources.get(name, True))


def load_settings(path: str | Path) -> Settings:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    roles = raw.get("roles", {})
    loc = raw.get("location", {})
    alerts = raw.get("alerts", {})
    boards = raw.get("boards", {})
    return Settings(
        internship_keywords=roles.get("internship_keywords", ["intern", "internship", "co-op"]),
        role_keywords=roles.get("role_keywords", []),
        list_categories=roles.get("list_categories", []),
        exclude_keywords=roles.get("exclude_keywords", []),
        seasons=roles.get("seasons", []),
        hide_past_seasons=roles.get("hide_past_seasons", True),
        allow_remote=loc.get("allow_remote", True),
        allow_unknown=loc.get("allow_unknown", True),
        include_places=loc.get("include", []),
        exclude_places=loc.get("exclude", []),
        alerts_enabled=alerts.get("enabled", True),
        max_age_days=alerts.get("max_age_days", 3),
        max_individual_alerts=alerts.get("max_individual_alerts", 8),
        sources=raw.get("sources", {}),
        always_check=boards.get("always_check", []),
        skip=boards.get("skip", []),
    )


def _kw_regex(words: list[str]) -> re.Pattern | None:
    words = [w.strip() for w in words if w and w.strip()]
    if not words:
        return None
    parts = []
    for w in sorted(words, key=len, reverse=True):
        esc = re.escape(w.lower()).replace(r"\ ", r"[\s\-]+")
        parts.append(rf"(?<![a-z0-9]){esc}(?![a-z0-9])")
    return re.compile("|".join(parts), re.I)


class Matcher:
    def __init__(self, s: Settings):
        self.s = s
        self.intern_re = _kw_regex(s.internship_keywords)
        self.role_re = _kw_regex(s.role_keywords)
        self.exclude_re = _kw_regex(s.exclude_keywords)
        self.categories = {c.lower() for c in s.list_categories}
        self.seasons = [x.lower() for x in s.seasons]

    def title_ok(self, title: str, category: str | None = None) -> bool:
        t = title or ""
        if self.intern_re and not self.intern_re.search(t):
            return False
        if self.exclude_re and self.exclude_re.search(t):
            return False
        if self.role_re is None:
            return True
        if category and category.lower() in self.categories:
            return True
        return bool(self.role_re.search(t))

    def season_ok(self, season: str | None, title: str = "") -> bool:
        if self.s.hide_past_seasons and season_is_past(season or detect_season(title)):
            return False
        if not self.seasons:
            return True
        hay = f"{season or ''} {title}".lower()
        if not (season or SEASON_RE.search(title or "")):
            return True  # unknown season: keep it rather than miss it
        return any(x in hay for x in self.seasons)

    def location_ok(self, locations: list[str], remote_flag: bool | None = None) -> tuple[bool, str]:
        """Returns (keep, label) where label is 'US', 'Remote', or 'Unclear'."""
        verdict = us_verdict(locations, remote_flag)
        if verdict in ("us", "remote") and (self.s.include_places or self.s.exclude_places):
            if not places_ok(locations, remote_flag, self.s.include_places, self.s.exclude_places):
                return False, "Excluded place"
        if verdict == "us":
            return True, "US"
        if verdict == "remote":
            return self.s.allow_remote, "Remote"
        if verdict == "unknown":
            return self.s.allow_unknown, "Unclear"
        return False, "Non-US"


SEASON_RE = re.compile(r"\b(spring|summer|fall|autumn|winter)\b(?:\s*['’]?\s*(20\d\d|\d\d))?", re.I)


# when each internship season is over (month, day)
SEASON_END = {"spring": (6, 30), "summer": (9, 30), "fall": (12, 31), "autumn": (12, 31), "winter": (4, 30)}


def season_is_past(season: str | None, today=None) -> bool:
    """True only if every season named has a year and has already ended (e.g. 'Summer 2026' in Nov 2026)."""
    from datetime import date
    if not season:
        return False
    today = today or date.today()
    found = re.findall(r"\b(spring|summer|fall|autumn|winter)\b\s*(20\d\d)", season, re.I)
    if not found or len(found) < len(re.findall(r"\b(spring|summer|fall|autumn|winter)\b", season, re.I)):
        return False
    return all(date(int(y), *SEASON_END[name.lower()]) < today for name, y in found)


def detect_season(title: str, terms: list[str] | str | None = None) -> str | None:
    if isinstance(terms, list):
        terms = [t for t in terms if t and t.upper() != "N/A"]
        if terms:
            return ", ".join(terms)
    elif isinstance(terms, str) and terms and terms.lower() not in ("null", "n/a"):
        return terms
    m = SEASON_RE.search(title or "")
    if m:
        season = m.group(1).title()
        if m.group(2):
            yr = m.group(2)
            season += " " + (yr if len(yr) == 4 else "20" + yr)
        return season
    return None


# ---- location ----------------------------------------------------------------

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY",
    "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND",
    "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}
US_STATE_NAMES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana",
    "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "district of columbia",
]
US_CITIES = [
    "san francisco", "bay area", "silicon valley", "san jose", "palo alto", "mountain view", "sunnyvale",
    "santa clara", "menlo park", "redwood city", "oakland", "los angeles", "san diego", "seattle",
    "bellevue", "redmond", "kirkland", "new york", "nyc", "brooklyn", "boston", "cambridge, ma", "austin",
    "dallas", "houston", "chicago", "denver", "boulder", "atlanta", "miami", "pittsburgh", "philadelphia",
    "washington, d.c", "washington dc", "arlington", "salt lake city", "phoenix", "portland", "detroit",
    "minneapolis", "raleigh", "durham", "nashville", "columbus", "irvine",
]
NON_US = [
    "canada", "toronto", "vancouver, bc", "british columbia", "montreal", "ontario", "quebec", "ottawa",
    "waterloo, on", "calgary", "united kingdom", "uk", "england", "london", "scotland", "ireland", "dublin",
    "germany", "berlin", "munich", "france", "paris", "netherlands", "amsterdam", "spain", "madrid",
    "barcelona", "portugal", "lisbon", "italy", "poland", "warsaw", "switzerland", "zurich", "sweden",
    "stockholm", "denmark", "norway", "finland", "belgium", "austria", "czech", "romania", "hungary",
    "greece", "turkey", "istanbul", "israel", "tel aviv", "india", "bangalore", "bengaluru", "hyderabad",
    "pune", "chennai", "mumbai", "delhi", "gurgaon", "noida", "singapore", "japan", "tokyo", "china",
    "beijing", "shanghai", "shenzhen", "hong kong", "taiwan", "taipei", "korea", "seoul", "vietnam",
    "philippines", "manila", "indonesia", "malaysia", "thailand", "australia", "sydney", "melbourne",
    "new zealand", "mexico", "brazil", "sao paulo", "são paulo", "argentina", "colombia", "chile", "peru",
    "costa rica", "uae", "dubai", "saudi", "egypt", "nigeria", "kenya", "south africa", "emea", "apac",
    "latam", "europe", "asia",
]
CA_PROVINCES = {"ON", "BC", "QC", "AB", "MB", "NS", "NB", "NL", "PE", "SK", "YT", "NT", "NU"}
US_SHORTHAND = {"SF", "LA", "NYC", "SOUTH SF", "DC", "SOCAL", "NORCAL", "SV"}
_STATE_CODE_RE = re.compile(r"(?:,\s*|\b(?:us|usa)[\s\-,]+)([A-Z]{2})\b")
_REMOTE_RE = re.compile(r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.I)


def _has_any(text: str, words: list[str]) -> bool:
    return any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text) for w in words)


def _one_location(loc: str) -> str:
    raw = (loc or "").strip()
    if not raw:
        return "unknown"
    low = raw.lower()
    if re.search(r"\b(united states|usa|u\.s\.)", low) or re.search(r"(?<![A-Za-z])US(?![A-Za-z])", raw):
        return "us"
    for m in _STATE_CODE_RE.finditer(raw):
        if m.group(1) in US_STATES:
            return "us"
        if m.group(1) in CA_PROVINCES:
            return "non_us"
    if raw.upper() in US_SHORTHAND:
        return "us"
    if re.match(r"^US-[A-Z]{2}\b", raw):
        return "us"
    if _has_any(low, NON_US):
        return "non_us"
    if _has_any(low, US_STATE_NAMES) or _has_any(low, US_CITIES):
        return "us"
    if _REMOTE_RE.search(low):
        return "remote"
    return "unknown"


def us_verdict(locations: list[str], remote_flag: bool | None = None) -> str:
    """'us' | 'remote' | 'unknown' | 'non_us' for a whole posting."""
    verdicts = [_one_location(l) for l in (locations or []) if l and l.strip()]
    if "us" in verdicts:
        return "us"
    if "remote" in verdicts:
        return "remote"
    if not verdicts:
        return "remote" if remote_flag else "unknown"
    if all(v == "non_us" for v in verdicts):
        return "non_us"
    if remote_flag and "non_us" not in verdicts:
        return "remote"
    return "unknown" if "non_us" not in verdicts else "non_us"


# ---- include / exclude places ----------------------------------------------------

STATE_NAME_BY_CODE = dict(zip(sorted(US_STATES - {"DC", "PR"}), [
    "alaska", "alabama", "arkansas", "arizona", "california", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "iowa", "idaho", "illinois", "indiana", "kansas", "kentucky",
    "louisiana", "massachusetts", "maryland", "maine", "michigan", "minnesota", "missouri", "mississippi",
    "montana", "north carolina", "north dakota", "nebraska", "new hampshire", "new jersey", "new mexico",
    "nevada", "new york", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "virginia", "vermont", "washington", "wisconsin",
    "west virginia", "wyoming"]))
STATE_NAME_BY_CODE.update({"DC": "district of columbia", "PR": "puerto rico"})
# shorthand cities that lists use without a state
CITY_STATE = {"sf": "CA", "south sf": "CA", "la": "CA", "bay area": "CA", "silicon valley": "CA",
              "nyc": "NY", "seattle": "WA", "boston": "MA", "austin": "TX", "chicago": "IL"}


def _place_matches(loc: str, place: str) -> bool:
    p = place.strip()
    if not p:
        return False
    low = loc.lower()
    if p.lower() == "remote":
        return bool(_REMOTE_RE.search(low))
    if len(p) == 2 and p.isalpha():            # a state code like "CA"
        code = p.upper()
        if re.search(rf"(?:,\s*|\bUS-){code}\b", loc):
            return True
        name = STATE_NAME_BY_CODE.get(code)
        other_code = any(m.group(1) != code and m.group(1) in US_STATES for m in _STATE_CODE_RE.finditer(loc))
        if name and not other_code and re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low):
            return True   # e.g. "Seattle, Washington", but not "Washington, DC"
        return CITY_STATE.get(low.strip()) == code
    return re.search(rf"(?<![a-z]){re.escape(p.lower())}(?![a-z])", low) is not None


def places_ok(locations: list[str], remote_flag, include: list[str], exclude: list[str]) -> bool:
    """Keep a posting if at least one of its locations is included (or include is empty)
    and that location isn't excluded. Remote counts as the place "Remote"."""
    locs = [l for l in (locations or []) if l and l.strip()] or (["Remote"] if remote_flag else [])
    if not locs:
        return True
    for loc in locs:
        if exclude and any(_place_matches(loc, x) for x in exclude):
            continue
        if not include or any(_place_matches(loc, x) for x in include):
            return True
    return False
