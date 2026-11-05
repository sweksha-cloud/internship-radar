"""What the radar remembers between scans (stored as JSON on the repo's radar-state branch)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .model import Posting

# Anything that looks like an internship is stored, whatever your settings say. Your settings are
# applied when alerting and when building the page, so changing them takes effect right away and
# never makes old postings look "new".
BROAD_INTERN_RE = re.compile(
    r"(?<![a-z])(intern|interns|internship|internships|co[\s-]?op|apprentice|apprenticeship|"
    r"trainee|student|summer analyst|summer associate|new grad)(?![a-z])", re.I)

KEEP_DAYS = 60


class State:
    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.records: dict[str, dict] = self._load("postings.json", {})
        self.meta: dict = self._load("meta.json", {})
        self.meta.setdefault("initialized_sources", [])
        self.meta.setdefault("boards", {})
        self.meta.setdefault("list_etags", {})
        self.meta.setdefault("fail_counts", {})
        self.meta.setdefault("hn", {"thread_id": None, "seen_ids": []})
        self.meta.setdefault("runs", 0)
        self._ct_index = {}
        for k, r in self.records.items():
            self._ct_index.setdefault(r.get("ct_key", ""), k)

    def _load(self, name, default):
        p = self.folder / name
        if p.exists():
            try:
                return json.loads(p.read_text())
            except ValueError:
                pass
        return default

    def save(self):
        (self.folder / "postings.json").write_text(json.dumps(self.records, separators=(",", ":")))
        (self.folder / "meta.json").write_text(json.dumps(self.meta, indent=1))

    @property
    def first_run(self) -> bool:
        return self.meta["runs"] == 0

    def is_initialized(self, source_id: str) -> bool:
        return source_id in self.meta["initialized_sources"]

    def mark_initialized(self, source_id: str):
        if source_id not in self.meta["initialized_sources"]:
            self.meta["initialized_sources"].append(source_id)

    def upsert(self, p: Posting, source_id: str, run_ts: str, quiet: bool) -> tuple[str, bool]:
        """Add or update a posting. Returns (record_key, is_new)."""
        key = p.key
        rec_key = key if key in self.records else None
        if rec_key is None:
            existing = self._ct_index.get(p.ct_key)
            if existing and existing in self.records:
                rec_key = existing
        if rec_key is None:
            self.records[key] = {
                "company": p.company, "title": p.title, "url": p.url, "locations": p.locations,
                "remote": p.remote, "season": p.season, "posted_at": p.posted_at,
                "category": p.category, "board": p.board, "ct_key": p.ct_key,
                "first_seen": run_ts, "last_seen": run_ts, "quiet": quiet, "closed": False,
                "first_source": p.source, "seen_by": {source_id: run_ts},
                "first_seen_by": {source_id: run_ts},
            }
            self._ct_index.setdefault(p.ct_key, key)
            return key, True
        r = self.records[rec_key]
        r["last_seen"] = run_ts
        r["closed"] = False
        r["seen_by"][source_id] = run_ts
        r.setdefault("first_seen_by", {}).setdefault(source_id, run_ts)
        # prefer a direct company link over a list's redirect link
        if r.get("first_source", "").startswith("list:") and not p.source.startswith("list:"):
            r["url"] = p.url
        for f in ("season", "posted_at", "category", "board"):
            if not r.get(f) and getattr(p, f):
                r[f] = getattr(p, f)
        if p.locations and not r.get("locations"):
            r["locations"] = p.locations
        if p.remote and not r.get("remote"):
            r["remote"] = True
        return rec_key, False

    def mark_closed(self, checked_ok: set[str], run_ts: str):
        """A posting is closed when every source that used to list it was checked and no longer does."""
        for r in self.records.values():
            sources = r.get("seen_by", {})
            if not sources or any(s.startswith("hn") for s in sources):
                continue
            gone = [s for s, ts in sources.items() if s in checked_ok and ts != run_ts]
            unknown = [s for s in sources if s not in checked_ok]
            if gone and not unknown and len(gone) == len(sources):
                r["closed"] = True

    def prune(self, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
        for k in [k for k, r in self.records.items() if r.get("last_seen", "") < cutoff]:
            del self.records[k]
        hn = self.meta["hn"]
        hn["seen_ids"] = hn["seen_ids"][-3000:]
