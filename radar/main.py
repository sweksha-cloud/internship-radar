"""Run one scan:  python -m radar  [--state state] [--site site] [--settings settings.toml]"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from .filters import Matcher, load_settings
from .model import now_iso
from .notify import send_alerts
from .page import build_page
from .sources import hackernews, lists, yc
from .sources.ats import FETCHERS
from .state import BROAD_INTERN_RE, State

SKIP_AFTER_FAILS = 5      # stop checking a board after this many failed scans in a row...
RETRY_EVERY_RUNS = 50     # ...but retry it now and then


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scan for new internship postings.")
    ap.add_argument("--state", default="state")
    ap.add_argument("--site", default="site")
    ap.add_argument("--settings", default="settings.toml")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args(argv)

    t0 = time.time()
    settings = load_settings(args.settings)
    matcher = Matcher(settings)
    state = State(args.state)
    run_ts = now_iso()
    health: dict = {"run_at": run_ts, "sources": {}, "boards": {}}
    checked_ok: set[str] = set()
    new_keys: list[str] = []

    def take(postings, source_id: str):
        quiet = state.first_run or not state.is_initialized(source_id)
        n = 0
        for p in postings:
            if not BROAD_INTERN_RE.search(p.title or ""):
                continue
            key, is_new = state.upsert(p, source_id, run_ts, quiet)
            n += 1
            if is_new and not quiet:
                new_keys.append(key)
        checked_ok.add(source_id)
        state.mark_initialized(source_id)
        return n

    # 1. community lists: postings + board discovery
    if settings.source_on("lists"):
        for name, url in lists.LISTS.items():
            sid = f"list:{name}"
            try:
                items, etag = lists.fetch_list(name, url, state.meta["list_etags"].get(name))
                state.meta["list_etags"][name] = etag
                if items is None:
                    health["sources"][sid] = {"ok": True, "note": "unchanged since last scan"}
                    continue
                n = take(lists.to_postings(name, items), sid)
                found = lists.discover_boards(items)
                state.meta["boards"].update(found)
                health["sources"][sid] = {"ok": True, "internships": n, "boards_found": len(found)}
            except Exception as e:
                health["sources"][sid] = {"ok": False, "error": str(e)[:200]}
            print(f"[{sid}] {health['sources'][sid]}")

    # 2. company job boards, checked directly
    # drop board names saved by an older version that misread a language code (".../en-us") as the board
    for b in [b for b in state.meta["boards"] if b.startswith("workday:") and re.search(r"/[a-z]{2}-[a-z]{2}$", b, re.I)]:
        del state.meta["boards"][b]
    boards = dict(state.meta["boards"])
    for b in settings.always_check:
        boards.setdefault(b, b.split(":", 1)[1].split("/")[0].split(".")[0])
    for b in settings.skip:
        boards.pop(b, None)
    fails = state.meta["fail_counts"]
    todo = []
    for b in boards:
        system = b.split(":", 1)[0]
        if system not in FETCHERS or not settings.source_on(system):
            continue
        if fails.get(b, 0) >= SKIP_AFTER_FAILS and state.meta["runs"] % RETRY_EVERY_RUNS:
            continue
        todo.append(b)

    def run_board(b):
        system, board = b.split(":", 1)
        return b, FETCHERS[system](board)

    per_system = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_board, b): b for b in todo}
        for fut in as_completed(futs):
            b = futs[fut]
            system = b.split(":", 1)[0]
            stats = per_system.setdefault(system, {"boards_ok": 0, "failed": 0, "internships": 0})
            try:
                _, postings = fut.result()
                company = boards.get(b)
                for p in postings:
                    if company and p.company.lower() in (b.split(":", 1)[1].lower(), b.split(":", 1)[1].split(".")[0].lower()):
                        p.company = company
                stats["internships"] += take(postings, b)
                stats["boards_ok"] += 1
                fails.pop(b, None)
            except Exception as e:
                stats["failed"] += 1
                fails[b] = fails.get(b, 0) + 1
                health["boards"][b] = str(e)[:120]
    for system, stats in per_system.items():
        health["sources"][system] = {"ok": stats["boards_ok"] > 0, **stats}
        print(f"[{system}] {stats}")

    # 3. YC jobs board
    if settings.source_on("yc"):
        try:
            n = take(yc.fetch_yc(), "yc")
            health["sources"]["yc"] = {"ok": True, "internships": n}
        except Exception as e:
            health["sources"]["yc"] = {"ok": False, "error": str(e)[:200]}
        print(f"[yc] {health['sources']['yc']}")

    # 4. Hacker News "Who is hiring?"
    if settings.source_on("hackernews"):
        hn = state.meta["hn"]
        try:
            tid = hackernews.latest_thread_id()
            if tid and tid != hn.get("thread_id"):
                hn["thread_id"], hn["seen_ids"] = tid, []
            if tid:
                postings, read = hackernews.fetch_new_comments(tid, set(hn["seen_ids"]))
                hn["seen_ids"].extend(read)
                sid = f"hn:{tid}"
                n = take(postings, sid)
                health["sources"]["hackernews"] = {"ok": True, "internships": n, "comments_read": len(read)}
            else:
                health["sources"]["hackernews"] = {"ok": False, "error": "no current thread found"}
        except Exception as e:
            health["sources"]["hackernews"] = {"ok": False, "error": str(e)[:200]}
        print(f"[hackernews] {health['sources']['hackernews']}")

    # 5. closed postings, alerts, page
    state.mark_closed(checked_ok, run_ts)
    state.prune()
    state.meta["runs"] += 1
    state.meta["last_run"] = run_ts

    max_age = timedelta(days=settings.max_age_days)
    now = datetime.now(timezone.utc)
    alerts = []
    for k in new_keys:
        r = state.records.get(k)
        if not r or r.get("closed"):
            continue
        if not matches(matcher, r):
            continue
        if r.get("posted_at") and now - datetime.fromisoformat(r["posted_at"]) > max_age:
            continue
        alerts.append(r)

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    page_url = os.environ.get("RADAR_PAGE_URL") or (
        f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if "/" in repo else None)
    sent = 0
    if settings.alerts_enabled and not args.no_notify:
        sent = send_alerts(alerts, page_url, settings.max_individual_alerts)

    health["duration_s"] = round(time.time() - t0, 1)
    health["new_postings"] = len(new_keys)
    health["new_matching"] = len(alerts)
    health["alerts_sent"] = sent
    health["boards_checked"] = len(todo)
    health["boards_known"] = len(boards)
    (state.folder / "health.json").write_text(json.dumps(health, indent=1))
    state.save()

    shown = build_page(state, matcher, settings, health, args.site, repo)
    print(f"done in {health['duration_s']}s: {len(new_keys)} new, {len(alerts)} match your settings, "
          f"{sent} alerts sent, {shown} postings on the page")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"new_matching={len(alerts)}\n")


def matches(matcher: Matcher, r: dict) -> bool:
    if not matcher.title_ok(r.get("title", ""), r.get("category")):
        return False
    if not matcher.season_ok(r.get("season"), r.get("title", "")):
        return False
    ok, label = matcher.location_ok(r.get("locations") or [], r.get("remote"))
    r["loc_label"] = label
    return ok


if __name__ == "__main__":
    main()
