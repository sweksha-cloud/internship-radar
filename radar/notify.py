"""Phone alerts through ntfy (https://ntfy.sh): free, no account needed.

Install the ntfy app, subscribe to a long random topic name, and save the same name
as the repo secret NTFY_TOPIC. Anyone who knows the topic name can read it, so make it unguessable.
"""
from __future__ import annotations

import os

from .http import fetch


def send_alerts(new: list[dict], page_url: str | None, max_individual: int) -> int:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic or not new:
        return 0
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    sent = 0
    if len(new) > max_individual:
        lines = [f"• {r['company']}: {r['title']}" for r in new[:12]]
        if len(new) > 12:
            lines.append(f"…and {len(new) - 12} more")
        _publish(server, {
            "topic": topic, "title": f"{len(new)} new internships",
            "message": "\n".join(lines), "click": page_url or "", "tags": ["rotating_light"],
        })
        return 1
    for r in new:
        loc = ", ".join(r.get("locations") or []) or r.get("loc_label", "")
        _publish(server, {
            "topic": topic, "title": f"New: {r['company']}"[:120],
            "message": f"{r['title']}\n{loc}\nvia {r.get('first_source', '')}".strip(),
            "click": r["url"], "tags": ["briefcase"],
            "actions": ([{"action": "view", "label": "All postings", "url": page_url}] if page_url else []),
        })
        sent += 1
    return sent


def _publish(server: str, payload: dict):
    try:
        fetch(server, method="POST", body=payload, timeout=15, retries=1)
    except Exception as e:  # an alert failing must never fail the scan
        print(f"  ntfy alert failed: {e}")
