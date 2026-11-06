# Internship Radar

Finds new **United States** internship postings (summer, fall, winter, spring, co-op, US-remote) soon after they go live, sends a phone alert, and keeps a page of everything still open that you can check any time.

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
- **Change what it looks for:** see [Choosing what it searches for](#choosing-what-it-searches-for) below.
- **Change how often it scans:** edit the `cron` line in [`.github/workflows/radar.yml`](.github/workflows/radar.yml). `"17 */3 * * *"` = every 3 hours. `"17 */6 * * *"` = every 6 hours. `"17 14 * * *"` = once a day.

## Choosing what it searches for

Everything the radar looks for is set in [`settings.toml`](settings.toml), and every scan reads it first. To change it before a scan:

1. On the page, tap **Edit settings** (or open `settings.toml` on GitHub and click the pencil icon).
2. Change what you want, then click **Commit changes**.
3. Tap **Scan now**, then **Run workflow**. The page rebuilds with your new settings in a few minutes. You don't have to wait for the next scheduled scan.

The scanner still reads every internship it finds and only applies your settings when it builds the page and sends alerts. So when you change a setting, postings it already found appear or disappear right away, and old postings never come back looking "new".

| Setting | What it does | Example |
| --- | --- | --- |
| `internship_keywords` | The title must contain one of these to count as an internship | `["intern", "co-op", "apprenticeship"]` |
| `role_keywords` | The title must also contain one of these (the positions you want). `[]` = any internship | `["software", "machine learning", "data engineer"]` |
| `list_categories` | Community-list categories accepted even without a role keyword | `["Software", "AI/ML/Data"]` |
| `exclude_keywords` | Skip any title containing one of these | `["hardware", "finance", "senior"]` |
| `seasons` | Only these seasons. `[]` = any season | `["Summer 2027", "Spring 2027"]` |
| `hide_past_seasons` | Hide seasons that are already over | `true` |
| `include` | Only these US places. `[]` = anywhere in the US | `["CA", "WA", "New York", "Remote"]` |
| `exclude` | Never these places | `["TX", "Omaha"]` |
| `allow_remote` | Keep "Remote" postings that don't name a country | `false` |
| `allow_unknown` | Keep postings with no location | `false` |
| `[sources]` | Turn whole sources on or off | `workday = false` |
| `always_check` / `skip` | Company job boards to always check, or never check | `"greenhouse:stripe"` |

### Changing the roles and jobs it looks for

The positions it shows are controlled by two lists in `settings.toml`, under `[roles]`:

- **`role_keywords`:** the kinds of jobs you want. A posting's title must contain at least one of these.
- **`exclude_keywords`:** words that rule a job out. A title containing any of these is skipped, even if it matched a role keyword.

Each list is words in quotes, separated by commas, inside `[ ]`. Common changes:

| I want to… | Do this |
| --- | --- |
| **Add a kind of job** (e.g. game development) | Add it to `role_keywords`: `"game developer", "gameplay",` |
| **Stop seeing a kind of job** (e.g. firmware) | Delete `"firmware",` from `role_keywords`, **or** add `"firmware",` to `exclude_keywords` |
| **Only see software engineering** | Set `role_keywords = ["software", "swe", "sde", "developer", "backend", "frontend", "full stack"]` and `list_categories = ["Software", "Software Engineering"]` |
| **Only see AI / ML** | Set `role_keywords = ["machine learning", "ml", "ai", "deep learning", "llm", "nlp", "computer vision", "data science", "applied scientist", "research scientist"]` and `list_categories = ["AI/ML/Data", "Data Science, AI & Machine Learning"]` |
| **See every internship, any field** | Set `role_keywords = []` and `list_categories = []`, and trim `exclude_keywords` |
| **Allow a word that's currently excluded** (e.g. hardware) | Delete `"hardware",` from `exclude_keywords` |
| **Only certain seasons** | `seasons = ["Summer 2027", "Spring 2027"]` (`[]` = any season) |
| **Only certain places** | `include = ["CA", "WA", "Remote"]` under `[location]` (`[]` = anywhere in the US) |
| **Never certain places** | `exclude = ["TX", "Omaha"]` under `[location]` |

`list_categories` matters because the community lists tag each posting with a category (Software, AI/ML/Data, Quant, Hardware, Product). A posting in one of the listed categories is shown even if its title doesn't contain a role keyword. If you narrow `role_keywords`, narrow `list_categories` to match.

**Check your work:** after you commit, the **Tests** workflow under the Actions tab checks that `settings.toml` is still valid. A red ✗ usually means a missing quote, comma or bracket. Then tap **Scan now** to rebuild the page.

Keywords match whole words and ignore case, so `"ml"` matches "ML Intern" but not "HTML". For places, use a state code (`"CA"`), a state name (`"Texas"`), a city (`"Seattle"`) or `"Remote"`. A posting with several locations is kept if any one of them is allowed.

**United States only.** The radar keeps a posting only if at least one of its locations is in the US: a US city or state, or remote within the US ("Remote - US"). Postings only outside the US are always dropped. Postings that say just "Remote" or give no location are dropped too, since they could be anywhere. Set `allow_remote` or `allow_unknown` to `true` to keep them.

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
