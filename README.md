# Internship Radar

Finds new US internship postings (summer, fall, winter, spring, co-op, remote) soon after they go live, sends a phone alert, and keeps a page of everything still open that you can check any time.

Community internship lists are great but can lag behind companies by hours or days. Internship Radar uses them to **discover** which companies hire interns, then checks those companies' job boards **directly**.

## What it checks

| Source | How |
| --- | --- |
| Company job boards on **Greenhouse, Lever, Ashby** | Their official public job-board APIs |
| Company job boards on **Workday** | The JSON endpoint Workday's own careers pages use |
| **Community lists** (Simplify, vanshb03) | Every posting link reveals a company's job board, so the radar finds ~2,000 boards automatically. The lists are also a backup source of postings. |
| **YC jobs board** | The public ycombinator.com/jobs pages |
| **Hacker News "Who is hiring?"** | The official Hacker News API. Only new comments are read each scan. |

One connector per job system covers every company that uses it, so adding a company never needs new code. Companies on fully custom careers sites (Google, Meta, Apple, Microsoft, Amazon…) are covered through the lists. For those, also turn on each company's own job alerts.

## Using it

- **The page:** `https://<your-username>.github.io/internship-radar/`. Newest first, with search, filters, and a "New since my last visit" toggle.
- **Mark done:** each posting has a **Mark done** button (for ones you applied to or don't want). Done postings are hidden, never deleted. Turn on **Show done** to see them again or undo. Done marks are saved in your browser, so your phone and laptop keep separate lists. Postings stay on the page for 60 days unless the company takes them down.
- **Scan now:** the page's **Scan now** button opens the workflow. Click **Run workflow**. (The GitHub mobile app can do this too: repo → Actions → Radar → Run workflow.)
- **Change what it looks for:** the page's **Edit settings** button opens [`settings.toml`](settings.toml). Edit the role keywords, excluded words, seasons, remote/unknown locations or alerts, then commit. The next scan uses them. Your settings are applied when alerting and building the page, so changing them never makes old postings look new.
- **Change how often it scans:** edit the `cron` line in [`.github/workflows/radar.yml`](.github/workflows/radar.yml). `"17 */3 * * *"` = every 3 hours. `"17 */6 * * *"` = every 6 hours. `"17 14 * * *"` = once a day.

## Setup (one time, about 10 minutes)

1. **Turn on the page:** repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Phone alerts:** install the free **ntfy** app (iOS/Android), tap **+**, and subscribe to a long random topic name, e.g. `radar-` plus 20 random letters. Anyone who knows the name can read it, so make it unguessable.
3. Save that same name as a repo secret: **Settings → Secrets and variables → Actions → New repository secret**, name `NTFY_TOPIC`.
4. Run the first scan: **Actions → Radar → Run workflow**.

The first scan records everything already open **without** alerting (otherwise you'd get thousands). From then on you're alerted only about postings that are new, match your settings, and were posted within `max_age_days`. The same "quiet first check" applies whenever the radar starts checking a newly found company board.

## How it works

```
GitHub Actions (every 3 hrs, or "Run workflow")
  → download community lists (only if changed) → discover company boards
  → check ~2,000 boards directly in parallel (Greenhouse / Lever / Ashby / Workday)
  → YC jobs board, Hacker News "Who is hiring?"
  → de-duplicate (same job from different sources = one posting)
  → apply settings.toml → phone alerts (ntfy) → rebuild the page (GitHub Pages)
  → save what it has seen to the radar-state branch
```

- **De-duplication:** jobs get a stable ID from their URL (Greenhouse job id, Lever/Ashby posting id, Workday requisition), with company + title as a fallback. The page shows which source found each posting first.
- **Closed postings** disappear once every source that listed them has been checked and no longer does.
- **Failing boards** are listed under "Scan health" on the page. A board that fails 5 scans in a row is paused and retried now and then.
- **Polite:** one request per board per scan, a clear User-Agent, and no logins.

## Run locally

```bash
python3 -m unittest discover -s tests -t .
python3 -m radar --state state --site site --no-notify   # then open site/index.html
```

Python 3.11+ and no dependencies.
