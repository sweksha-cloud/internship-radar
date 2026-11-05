import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from radar.filters import Matcher, load_settings, us_verdict, detect_season
from radar.model import Posting, job_key, parse_board
from radar.sources import ats, hackernews, yc
from radar.state import State

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"


def settings(**overrides):
    s = load_settings(ROOT / "settings.toml")
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class TitleFilters(unittest.TestCase):
    def setUp(self):
        self.m = Matcher(settings())

    def test_accepts_software_internships_of_any_kind(self):
        for t in ["Software Engineer Intern", "SWE Intern - Summer 2027", "Machine Learning Co-op (Spring 2027)",
                  "Backend Engineering Internship", "Data Science Intern", "Winter 2027 Software Co-Op",
                  "AI Research Intern", "Engineering Intern"]:
            self.assertTrue(self.m.title_ok(t), t)

    def test_rejects_non_internships_and_excluded(self):
        for t in ["Senior Software Engineer", "Internal Tools Engineer", "PhD Research Intern",
                  "Marketing Intern", "Sales Intern", "Software Engineering Manager"]:
            self.assertFalse(self.m.title_ok(t), t)

    def test_short_keywords_need_whole_words(self):
        self.assertFalse(self.m.title_ok("HTML Email Intern"))      # 'ml' must not match inside 'html'
        self.assertTrue(self.m.title_ok("ML Intern"))

    def test_list_category_counts_as_a_role(self):
        self.assertTrue(self.m.title_ok("Intern - Team Alpha", category="Software"))
        self.assertFalse(self.m.title_ok("Intern - Team Alpha", category="Product"))

    def test_empty_role_list_accepts_every_internship(self):
        m = Matcher(settings(role_keywords=[]))
        self.assertTrue(m.title_ok("Operations Intern"))

    def test_seasons(self):
        m = Matcher(settings(seasons=["Summer 2027"]))
        self.assertTrue(m.season_ok("Summer 2027"))
        self.assertFalse(m.season_ok("Fall 2026"))
        self.assertTrue(m.season_ok(None, "Software Intern"))   # unknown season is kept
        from datetime import date
        from radar.filters import season_is_past
        nov26 = date(2026, 11, 5)
        self.assertTrue(season_is_past("Summer 2026", nov26))
        self.assertTrue(season_is_past("Winter 2026", nov26))
        self.assertFalse(season_is_past("Fall 2026", nov26))
        self.assertFalse(season_is_past("Summer 2026, Summer 2027", nov26))
        self.assertFalse(season_is_past("Summer", nov26))
        self.assertFalse(season_is_past("Winter 2026, Spring", nov26))  # a season with no year: keep
        self.assertEqual(detect_season("SWE Intern - Summer '27"), "Summer 2027")
        self.assertEqual(detect_season("x", ["N/A"]), None)
        self.assertEqual(detect_season("x", ["Fall 2026", "Winter 2027"]), "Fall 2026, Winter 2027")


class Locations(unittest.TestCase):
    def test_us(self):
        for locs in [["San Jose, CA"], ["New York, NY"], ["US-MI-Detroit"], ["United States"], ["Remote - US"],
                     ["Seattle"], ["Austin, Texas"], ["London, ON", "Boston, MA"], ["Remote in USA"]]:
            self.assertEqual(us_verdict(locs), "us", locs)

    def test_remote_and_unknown(self):
        self.assertEqual(us_verdict(["Remote"]), "remote")
        self.assertEqual(us_verdict([]), "unknown")
        self.assertEqual(us_verdict([], remote_flag=True), "remote")

    def test_shorthand_and_provinces(self):
        self.assertEqual(us_verdict(["SF"]), "us")
        self.assertEqual(us_verdict(["South SF"]), "us")
        self.assertEqual(us_verdict(["Georgia"]), "us")
        self.assertEqual(us_verdict(["Mississauga, ON"]), "non_us")

    def test_non_us(self):
        for locs in [["Toronto, ON"], ["London, United Kingdom"], ["Bengaluru, India"], ["Remote - Canada"],
                     ["Berlin"], ["Vancouver, BC"]]:
            self.assertEqual(us_verdict(locs), "non_us", locs)

    def test_settings_switches(self):
        m = Matcher(settings(allow_remote=False))
        self.assertEqual(m.location_ok(["Remote"]), (False, "Remote"))
        self.assertEqual(m.location_ok(["Palo Alto, CA"]), (True, "US"))


class UrlIdentity(unittest.TestCase):
    def test_boards(self):
        self.assertEqual(parse_board("https://job-boards.greenhouse.io/axon/jobs/7245404003"), ("greenhouse", "axon"))
        self.assertEqual(parse_board("https://boards.greenhouse.io/embed/job_app?for=Stripe&token=1"), ("greenhouse", "stripe"))
        self.assertEqual(parse_board("https://jobs.lever.co/palantir/abc-123"), ("lever", "palantir"))
        self.assertEqual(parse_board("https://jobs.ashbyhq.com/ramp/abc"), ("ashby", "ramp"))
        self.assertEqual(parse_board("https://pae.wd1.myworkdayjobs.com/en-US/amentum_careers/job/US-MI/Intern_R1"),
                         ("workday", "pae.wd1/amentum_careers"))
        self.assertEqual(parse_board("https://wd5.myworkdaysite.com/recruiting/acme/External/job/X/Intern_R9"),
                         ("workday", "site:wd5/acme/External"))
        self.assertEqual(parse_board("https://intel.wd1.myworkdayjobs.com/en-us/External/job/X/Intern_JR1"),
                         ("workday", "intel.wd1/External"))  # lowercase language code is not the board
        self.assertIsNone(parse_board("https://www.metacareers.com/jobs/1"))

    def test_same_job_same_key_across_sources(self):
        self.assertEqual(job_key("https://job-boards.greenhouse.io/stripe/jobs/123?utm_source=Simplify"),
                         job_key("https://stripe.com/jobs/search?gh_jid=123"))
        self.assertEqual(job_key("https://copart.wd12.myworkdayjobs.com/copart/job/Dallas-TX/SWE-Intern_JR1"),
                         job_key("https://copart.wd12.myworkdayjobs.com/en-US/copart/job/Dallas-TX/SWE-Intern_JR1/apply"))

    def test_workday_server_grouping(self):
        self.assertEqual(ats._wd_server("nvidia.wd5/NVIDIAExternalCareerSite"), "wd5")
        self.assertEqual(ats._wd_server("site:wd3/acme/External"), "wd3")
        self.assertIs(ats._wd_slot("a.wd5/X"), ats._wd_slot("b.wd5/Y"))

    def test_workday_api_urls(self):
        self.assertEqual(ats.workday_urls("nvidia.wd5/NVIDIAExternalCareerSite")[0],
                         "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs")
        self.assertEqual(ats.workday_urls("site:wd5/acme/External")[0],
                         "https://wd5.myworkdaysite.com/wday/cxs/acme/External/jobs")


class Parsers(unittest.TestCase):
    def load(self, name):
        return json.loads((FIX / name).read_text())

    def test_greenhouse(self):
        ps = ats.parse_greenhouse("acme", self.load("greenhouse.json"))
        self.assertEqual(len(ps), 2)
        self.assertEqual(ps[0].title, "Software Engineer Intern, Summer 2027")
        self.assertEqual(ps[0].locations, ["San Francisco, CA", "New York, NY"])
        self.assertTrue(ps[0].posted_at.startswith("2026-11-04"))
        self.assertIn("gh_jid=4001", ps[1].url)  # company-domain URL keeps the job id

    def test_lever(self):
        ps = ats.parse_lever("acme", self.load("lever.json"))
        self.assertEqual(ps[0].title, "Backend Intern")
        self.assertTrue(ps[0].remote)
        self.assertEqual(ps[0].locations, ["Remote - US"])

    def test_ashby(self):
        ps = ats.parse_ashby("acme", self.load("ashby.json"))
        self.assertEqual(len(ps), 1)  # unlisted job dropped
        self.assertIn("United States", ps[0].locations)

    def test_workday(self):
        ps = ats.parse_workday("acme.wd5/External", self.load("workday.json"), "https://acme.wd5.myworkdayjobs.com/External")
        self.assertEqual(ps[0].url, "https://acme.wd5.myworkdayjobs.com/External/job/Austin-TX/Software-Intern_R100")
        self.assertIsNotNone(ps[0].posted_at)
        age = datetime.now(timezone.utc) - datetime.fromisoformat(ps[2].posted_at)
        self.assertGreaterEqual(age.days, 29)  # "Posted 30+ Days Ago" is old, so it never alerts

    def test_hn_comment(self):
        p = hackernews.parse_comment({"id": 5, "time": 1793800000,
            "text": "Acme Robotics | Software Engineering Intern | Boston, MA | Onsite<p>We build robots..."})
        self.assertEqual(p.company, "Acme Robotics")
        self.assertEqual(p.title, "Software Engineering Intern")
        self.assertEqual(p.locations, ["Boston, MA", "Onsite"])
        self.assertIsNone(hackernews.parse_comment({"id": 6, "text": "Acme | Senior Engineer | Remote"}))

    def test_yc_links_and_json(self):
        page = '<a href="/companies/acme/jobs/AbC1-software-engineer-intern">Software Engineer Intern</a>'
        ps = yc.parse_yc_html(page)
        self.assertEqual(ps[0].company, "Acme")
        blob = json.dumps({"props": {"jobs": [{"id": 9, "title": "ML Intern", "companyName": "Beta",
                                               "url": "/companies/beta/jobs/9-ml-intern", "location": "Remote"}]}})
        import html as h
        ps = yc.parse_yc_html(f'<div data-page="{h.escape(blob)}"></div>')
        self.assertEqual((ps[0].company, ps[0].title), ("Beta", "ML Intern"))


class StateBehavior(unittest.TestCase):
    def p(self, url="https://job-boards.greenhouse.io/acme/jobs/1", title="Software Intern", source="greenhouse"):
        return Posting(company="Acme", title=title, url=url, source=source, locations=["Austin, TX"])

    def test_dedupes_list_and_direct_board(self):
        with tempfile.TemporaryDirectory() as d:
            s = State(d)
            k1, new1 = s.upsert(self.p(url="https://job-boards.greenhouse.io/acme/jobs/1?utm_source=Simplify",
                                       source="list:Simplify"), "list:Simplify", "2026-11-05T00:00:00+00:00", False)
            k2, new2 = s.upsert(self.p(), "greenhouse:acme", "2026-11-05T03:00:00+00:00", False)
            self.assertTrue(new1)
            self.assertFalse(new2)
            self.assertEqual(k1, k2)
            r = s.records[k1]
            self.assertEqual(r["url"], "https://job-boards.greenhouse.io/acme/jobs/1")   # direct link preferred
            self.assertEqual(set(r["first_seen_by"]), {"list:Simplify", "greenhouse:acme"})

    def test_dedupes_by_company_and_title_when_urls_differ(self):
        with tempfile.TemporaryDirectory() as d:
            s = State(d)
            s.upsert(self.p(url="https://go.vansh.nyc/abc", source="list:vanshb03"), "list:vanshb03", "t1", False)
            _, new = s.upsert(self.p(), "greenhouse:acme", "t2", False)
            self.assertFalse(new)

    def test_closed_when_every_source_drops_it(self):
        with tempfile.TemporaryDirectory() as d:
            s = State(d)
            k, _ = s.upsert(self.p(), "greenhouse:acme", "t1", False)
            s.mark_closed({"greenhouse:acme"}, "t2")
            self.assertTrue(s.records[k]["closed"])

    def test_not_closed_if_a_source_was_not_checked(self):
        with tempfile.TemporaryDirectory() as d:
            s = State(d)
            k, _ = s.upsert(self.p(), "greenhouse:acme", "t1", False)
            s.mark_closed(set(), "t2")
            self.assertFalse(s.records[k]["closed"])

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as d:
            s = State(d)
            s.upsert(self.p(), "greenhouse:acme", "t1", False)
            s.meta["runs"] = 1
            s.save()
            s2 = State(d)
            self.assertEqual(len(s2.records), 1)
            self.assertFalse(s2.first_run)


class EndToEnd(unittest.TestCase):
    """Runs a full scan with fake sources: the first scan must stay quiet, the second must alert."""

    def test_first_scan_quiet_then_alerts_on_new(self):
        from unittest import mock
        from radar import main as radar_main
        from radar.sources import lists

        now = datetime.now(timezone.utc)
        gh = {"jobs": [{"id": 1, "title": "Software Engineer Intern", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
                        "location": {"name": "Austin, TX"}, "first_published": (now - timedelta(days=10)).isoformat()}]}
        sent = []

        def offline(board):
            raise OSError("offline in tests")

        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(lists, "fetch_list", return_value=([], None)), \
             mock.patch.dict(radar_main.FETCHERS, {"greenhouse": lambda b: ats.parse_greenhouse(b, gh) if b == "acme" else [],
                                                  "lever": offline, "ashby": offline, "workday": offline}), \
             mock.patch.object(radar_main, "send_alerts", side_effect=lambda new, url, mx: sent.append(list(new)) or len(new)), \
             mock.patch.object(radar_main.yc, "fetch_yc", return_value=[]), \
             mock.patch.object(radar_main.hackernews, "latest_thread_id", return_value=None):
            cfg = Path(d) / "settings.toml"
            cfg.write_text((ROOT / "settings.toml").read_text().replace('always_check = [', 'always_check = ["greenhouse:acme", ').replace(
                '"greenhouse:stripe"', '"greenhouse:acme2"'))
            args = ["--state", f"{d}/state", "--site", f"{d}/site", "--settings", str(cfg)]
            radar_main.main(args)
            self.assertEqual(sent, [[]])  # first scan: everything already open, no alerts
            gh["jobs"].append({"id": 2, "title": "ML Intern", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/2",
                               "location": {"name": "Remote - US"}, "first_published": now.isoformat()})
            gh["jobs"].append({"id": 3, "title": "Marketing Intern", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/3",
                               "location": {"name": "Austin, TX"}, "first_published": now.isoformat()})
            radar_main.main(args)
            self.assertEqual([r["title"] for r in sent[1]], ["ML Intern"])  # marketing filtered out by settings
            page = (Path(d) / "site" / "index.html").read_text()
            self.assertIn("ML Intern", page)
            self.assertNotIn("Marketing Intern", page)


if __name__ == "__main__":
    unittest.main()
