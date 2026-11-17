#!/usr/bin/env python3
"""
jword - hiring-signal lead engine (Claude skill edition).

Ported from the Hiring Signal Lead Engine n8n workflow. Claude does the web searching,
page reading and scoring; this script does the bookkeeping that must be exact:
search planning (every role x location, rotating query styles, dated to the current month),
result filtering (listing/search pages, closed or stale jobs, wrong location, agency posts),
keeping sources varied (no single website dominates), keyword scoring, de-duplication,
and the Excel export (Leads + Run Log).

Claude's web search does not honour `site:` filters, so Jword searches the open web and
balances by source website instead of by job board.

All state lives in one JSON file (default ./jword_run/state.json).

Commands (each prints JSON):
  init    --mode clients|jobs --roles "A, B" --locations "X, Y" [options]   start a run
  next                                                                      what to do next
  ingest  --results results.json                                            feed web-search results
  apply   --updates updates.json                                            feed verdicts / page checks / contacts
  status                                                                    progress summary
  plan                                                                      saved leads + what's left to do (contacts / applying)
  contacts --updates contacts.json                                          record emails found on public pages
  track   --updates track.json                                              record application / email outcomes
  profile-check --profile applicant_profile.json                            check the applicant profile before applying
  report                                                                    final status list (markdown) for the chat
  export  --out leads.xlsx                                                  write the Excel file
"""
from __future__ import annotations

import argparse
import difflib
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ============================================================================ configuration

# Friendly names for common sources (anything else is shown as its domain)
SOURCE_NAMES = {
    "linkedin.com": "LinkedIn", "indeed.com": "Indeed", "greenhouse.io": "Greenhouse", "lever.co": "Lever",
    "wellfound.com": "Wellfound", "builtin.com": "Built In", "builtinlondon.uk": "Built In",
    "glassdoor.com": "Glassdoor", "glassdoor.co.uk": "Glassdoor", "reed.co.uk": "Reed",
    "totaljobs.com": "Totaljobs", "cwjobs.co.uk": "CWJobs", "itjobswatch.co.uk": "IT Jobs Watch",
    "welcometothejungle.com": "Welcome to the Jungle", "otta.com": "Welcome to the Jungle",
    "recruitee.com": "Recruitee", "workable.com": "Workable", "teamtailor.com": "Teamtailor",
    "ashbyhq.com": "Ashby", "smartrecruiters.com": "SmartRecruiters", "bamboohr.com": "BambooHR",
    "personio.de": "Personio", "personio.com": "Personio", "jooble.org": "Jooble", "career.io": "Career.io",
    "wearedevelopers.com": "WeAreDevelopers", "stepstone.de": "StepStone", "bayt.com": "Bayt",
    "rozee.pk": "Rozee.pk", "naukri.com": "Naukri", "seek.com.au": "SEEK", "jobstreet.com": "JobStreet",
    "gumtree.com": "Gumtree", "grabjobs.co": "GrabJobs", "remoteok.com": "Remote OK",
    "weworkremotely.com": "We Work Remotely", "remotive.com": "Remotive", "dice.com": "Dice",
    "ziprecruiter.com": "ZipRecruiter", "ziprecruiter.co.uk": "ZipRecruiter", "monster.com": "Monster",
}
EXCLUDED_DOMAINS = ["youtube.com", "wikipedia.org", "facebook.com", "instagram.com", "reddit.com", "quora.com",
                    "medium.com", "x.com", "twitter.com", "tiktok.com", "pinterest.com"]
# URLs and titles of pages that list many jobs (search results, salary/stat pages), not one posting
LISTING_URL = re.compile(
    r"/find/|/q-|[?&](q|keywords?|search|page)=|/jobs?/search|/search/|-jobs-in-|/jobs-in-|/salar(y|ies)|"
    r"\.do($|\?)|/career-advice|/blog/|/companies/?$|/jobs/?$|/careers/?$", re.I)
LISTING_TITLE = [
    re.compile(r"\b\d[\d,]*\+?\s+(\w+\s+){0,5}jobs\b", re.I),      # "54,244 Flutter Developer Jobs"
    re.compile(r"\bjobs\s+(in|near|at|for)\b", re.I),               # "Flutter Developer Jobs in London"
    re.compile(r"^\s*(remote|top|best|latest|new)\b[^|:]{0,50}\bjobs\s*$", re.I),   # "Remote LLM Jobs"
    re.compile(r"\(with salaries\)|\bsalar(y|ies)\b|\bopen positions\b", re.I),
    re.compile(r"\b(vacancies|job openings|jobs and careers)\b", re.I),
    re.compile(r"^jobs?\s+(in|for)\b", re.I),
]
TRACKING_PARAMS = re.compile(r"^(utm_.*|trk.*|ref.*|src|source|from|fbclid|gclid|mc_.*|_hs.*|tk|cid|campaign.*)$", re.I)
# Listings you can't apply to without paying (membership sites that also hide the employer)
PAYWALL_HINTS = re.compile(
    r"available to (premium )?(members|subscribers)|premium membership|subscribe (today|now) to (get|see|view|unlock)|"
    r"(sign in|log in|login|register) to (view|see) (the )?(full|complete|job)|unlock (the )?(full )?job", re.I)
PAYWALL_DOMAINS = {"virtualvocations.com", "flexjobs.com"}
# A recruitment agency advertising for a hidden client (not a direct lead in clients mode)
AGENCY_HINTS = re.compile(
    r"\b(recruitment|recruiting|resourcing|staffing|headhunt\w*|talent solutions|"
    r"acting as an employment (agency|business)|our client|my client|on behalf of (a|our) client)\b", re.I)

# Platforms the user can prefer: (query hint, how to recognise a result's source)
PLATFORMS = {
    "Greenhouse": ("greenhouse", lambda src, d: d == "greenhouse.io"),
    "Lever": ("jobs.lever.co", lambda src, d: d == "lever.co"),
    "Ashby": ("ashbyhq", lambda src, d: d == "ashbyhq.com"),
    "Workable": ("workable", lambda src, d: d == "workable.com"),
    "LinkedIn": ("linkedin jobs", lambda src, d: d == "linkedin.com"),
    "Indeed": ("indeed", lambda src, d: d == "indeed.com"),
    "Wellfound": ("wellfound", lambda src, d: d == "wellfound.com"),
    "Built In": ("builtin", lambda src, d: src == "Built In"),
    "Company career pages": ("careers page", lambda src, d: d in ATS or src == d),   # employer's own site / ATS
    "Remote job boards": ("remotive", lambda src, d: d in REMOTE_BOARDS),
}
REMOTE_BOARDS = {"remotive.com", "arc.dev", "dailyremote.com", "weworkremotely.com", "remoteok.com", "remoteok.io",
                 "himalayas.app", "workingnomads.com", "jobicy.com", "remoterocketship.com", "remoteleaf.com",
                 "dynamitejobs.com", "wellfound.com", "remote.co", "justremote.co"}

# Live tests (Nov 2026): short, plain queries with a recency phrase ("posted 2 days ago") return dated
# postings from boards that print dates (Remotive, Wellfound, Arc, Built In, DailyRemote, local boards).
# Long "remote-first startup ..." wording returned mostly paywalled aggregators and undated pages.
QUERY_STYLES = [
    "{role} jobs {loc} posted {recent}",
    "{role} job {loc}",
    "{role} {loc} hiring {recent}",
    "{role} vacancy {loc} {month}",
    "{role} jobs in {loc} apply {recent}",
]
REMOTE_QUERY_STYLES = [
    "{role} remote job posted {recent}",
    "remote {role} jobs {recent}",
    "{role} remote worldwide job {month}",
    "{role} work from anywhere job posted {recent}",
    "{role} remote job apply now {year}",
]


# Board-scoped search, ported from the n8n workflow: each chosen board is searched with a site: filter,
# the board with the fewest saved jobs is served next, and a board that stops producing is marked dry.
# Live tests (Nov 2026): site: works in Claude's web search for rozee.pk, greenhouse.io, workable.com and
# others; LinkedIn *job pages* are not in its index, but site:linkedin.com returns LinkedIn *hiring posts*
# (often with an apply email). No API keys: only Claude's own search and fetch.
BOARD_CATALOG = {
    "open_web":   {"label": "Open web", "site": "", "weight": 1.2},
    "linkedin":   {"label": "LinkedIn hiring posts", "site": "linkedin.com", "weight": 1.4},
    "greenhouse": {"label": "Greenhouse", "site": "greenhouse.io", "weight": 1.0},
    "lever":      {"label": "Lever", "site": "jobs.lever.co", "weight": 1.0},
    "workable":   {"label": "Workable", "site": "workable.com", "weight": 1.0},
    "ashby":      {"label": "Ashby", "site": "jobs.ashbyhq.com", "weight": 0.8},
    "indeed":     {"label": "Indeed", "site": "indeed.com", "weight": 1.0},
    "wellfound":  {"label": "Wellfound", "site": "wellfound.com/jobs", "weight": 1.0},
    "builtin":    {"label": "Built In", "site": "builtin.com/job", "weight": 1.0},
    "remotive":   {"label": "Remotive", "site": "remotive.com/remote/jobs", "weight": 1.0},
    "arc":        {"label": "Arc", "site": "arc.dev/remote-jobs", "weight": 0.8},
    "dailyremote": {"label": "DailyRemote", "site": "dailyremote.com/remote-job", "weight": 0.8},
    "weworkremotely": {"label": "We Work Remotely", "site": "weworkremotely.com/remote-jobs", "weight": 0.8},
}
REGIONAL_BOARDS = {          # country -> boards that print dates and are in the search index
    "pakistan": [("rozee", "Rozee.pk", "rozee.pk"), ("hiredpk", "Hired.pk", "hired.pk/jobs"),
                 ("taraki", "Taraki", "jobs.taraki.co/jobs")],
    "uae": [("bayt_ae", "Bayt", "bayt.com")], "saudi arabia": [("bayt_sa", "Bayt", "bayt.com")],
    "qatar": [("bayt_qa", "Bayt", "bayt.com")], "egypt": [("wuzzuf", "Wuzzuf", "wuzzuf.net/jobs")],
    "india": [("naukri", "Naukri", "naukri.com/job-listings")],
    "united kingdom": [("reed", "Reed", "reed.co.uk/jobs"), ("totaljobs", "Totaljobs", "totaljobs.com/job")],
    "germany": [("stepstone", "StepStone", "stepstone.de/stellenangebote")],
    "united states": [("builtin_us", "Built In", "builtin.com/job")],
}
PLATFORM_BOARDS = {
    "Company career pages": ["greenhouse", "lever", "workable", "ashby"], "Greenhouse": ["greenhouse"],
    "Lever": ["lever"], "Ashby": ["ashby"], "Workable": ["workable"], "LinkedIn": ["linkedin"],
    "Indeed": ["indeed"], "Wellfound": ["wellfound"], "Built In": ["builtin"],
    "Remote job boards": ["remotive", "arc", "dailyremote", "weworkremotely"],
}
BOARD_DRY_AFTER = 2          # searches in a row with nothing new -> the board is dry


def country_of(loc: str) -> str:
    l = (loc or "").lower()
    for country, (names, cities) in LOCATION_GROUPS.items():
        if any(n in l for n in names + cities):
            return country
    return ""


def build_boards(cfg) -> list:
    """The boards this run searches, in priority order, each with the locations it serves."""
    plats = cfg.get("platforms") or []
    locs = cfg["locations"]
    boards, seen = [], set()

    def add(key, label=None, site=None, weight=1.0, only=None, dated=False):
        if key in seen:
            return
        seen.add(key)
        base = BOARD_CATALOG.get(key, {})
        boards.append({"name": key, "label": label or base.get("label", key), "site": base.get("site", "") if site is None else site,
                       "weight": base.get("weight", weight), "locs": only, "searches": 0, "dry_streak": 0,
                       "dated": dated})

    if plats:
        for pl in plats:
            for k in PLATFORM_BOARDS.get(pl, []):
                add(k)
        if not cfg.get("platforms_only"):
            add("open_web")
    else:                                            # "Anywhere": open web + LinkedIn posts + regional + ATS
        add("open_web")
        add("linkedin")
        for loc in locs:
            for key, label, site in REGIONAL_BOARDS.get(country_of(loc), []):
                if key in seen:
                    boards[[b["name"] for b in boards].index(key)]["locs"].append(loc)
                else:
                    add(key, label, site, 1.1, [loc], dated=True)
        add("greenhouse")
        add("workable")
        add("lever")
        if any(is_remote(l) or is_anywhere(l) for l in locs):
            add("remotive")
            add("dailyremote")
    return boards


def board_saved(st, name) -> int:
    return sum(1 for c in st["candidates"] if c.get("board") == name and c["status"] in ("saved", "ready") + IN_FLIGHT)


def board_dry(st, b) -> bool:
    if b["dry_streak"] >= BOARD_DRY_AFTER:
        return True
    pending = any(c.get("board") == b["name"] and c["status"] in ("queued", "ready") + IN_FLIGHT for c in st["candidates"])
    return b["searches"] >= 4 and board_saved(st, b["name"]) == 0 and not pending


def pick_board(st, loc: str = "") -> dict:
    """Serve the board furthest behind its share (weighted), skipping dry ones; reset if all are dry.
    Only boards that serve `loc` are considered (regional boards serve their own country)."""
    boards = st.setdefault("boards", build_boards(st["config"]))
    serving = [b for b in boards if not b.get("locs") or loc in b["locs"]] or boards
    live = [b for b in serving if not board_dry(st, b)]
    if not live:
        for b in serving:
            b["dry_streak"] = 0
        live = serving
    order = {b["name"]: i for i, b in enumerate(boards)}
    return min(live, key=lambda b: (board_saved(st, b["name"]) / b["weight"], b["searches"] / b["weight"], order[b["name"]]))


def date_hints(cfg) -> list:
    """Month words that dated job boards print on every listing ("Posting Date: Nov 09, 2026").
    Anchoring a site: query on them makes the search index return this month's listings, with the
    date in the snippet, instead of years-old pages (measured on Rozee: 1 dated hit -> 3 of the first 3)."""
    w = cfg.get("window")
    end = dt.date.fromisoformat(w["end"]) if w else dt.date.today()
    start = dt.date.fromisoformat(w["start"]) if w else end - dt.timedelta(days=30)
    months, d = [], end
    while (d.year, d.month) >= (start.year, start.month) and len(months) < 2:
        mon = d.strftime("%b")
        months.append(f'"{mon}" "{d.year}"')
        d = d.replace(day=1) - dt.timedelta(days=1)
    return months


def recency_phrases(cfg) -> list:
    """Words that make search engines prefer fresh postings, matched to the user's window."""
    w = cfg.get("window")
    if not w:
        return ["this month", "this week", "recently"]
    days = (dt.date.fromisoformat(w["end"]) - dt.date.fromisoformat(w["start"])).days
    if days <= 1:
        return ["today", "hours ago", "1 day ago"]
    if days <= 3:
        return ["2 days ago", "today", "yesterday"]
    if days <= 7:
        return ["2 days ago", "this week", "5 days ago"]
    if days <= 14:
        return ["this week", "1 week ago", "10 days ago"]
    return ["this week", "2 weeks ago", "this month"]


CLOSED_PHRASES = [
    "no longer accepting applications", "no longer accepting", "job is no longer available",
    "job no longer available", "no longer available", "this job has expired", "job has expired",
    "that job has expired", "job expired", "position has been filled", "position is filled",
    "role has been filled", "already been filled", "has been filled", "applications are closed",
    "applications closed", "this job is closed", "job is closed", "job is now closed", "is now closed",
    "vacancy closed", "vacancy has closed", "not accepting applications", "posting has closed",
    "this position is no longer", "job was removed", "job has been removed", "job not found",
    "this job is no longer", "listing has expired", "advert has expired",
]
CLOSED_RE = re.compile("|".join(re.escape(p) for p in CLOSED_PHRASES), re.I)

LOCATION_GROUPS = {
    "united states": (["united states", "usa", "u.s."], ["new york", "san francisco", "seattle", "austin", "boston", "chicago", "los angeles", "denver", "atlanta", "miami", "dallas", "washington dc"]),
    "united kingdom": (["united kingdom", "uk", "england", "scotland", "great britain"], ["london", "manchester", "edinburgh", "birmingham", "bristol", "cambridge", "oxford", "glasgow", "leeds"]),
    "canada": (["canada"], ["toronto", "vancouver", "montreal", "ottawa", "calgary"]),
    "germany": (["germany", "deutschland"], ["berlin", "munich", "hamburg", "frankfurt", "cologne"]),
    "netherlands": (["netherlands", "holland"], ["amsterdam", "rotterdam", "the hague", "utrecht", "eindhoven"]),
    "ireland": (["ireland"], ["dublin", "cork"]),
    "france": (["france"], ["paris", "lyon"]),
    "spain": (["spain"], ["madrid", "barcelona"]),
    "sweden": (["sweden"], ["stockholm"]),
    "poland": (["poland"], ["warsaw", "krakow"]),
    "uae": (["uae", "united arab emirates", "emirates"], ["dubai", "abu dhabi", "sharjah"]),
    "saudi arabia": (["saudi arabia", "saudi", "ksa"], ["riyadh", "jeddah", "dammam"]),
    "qatar": (["qatar"], ["doha"]),
    "singapore": (["singapore"], []),
    "australia": (["australia"], ["sydney", "melbourne", "brisbane", "perth"]),
    "india": (["india"], ["bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "pune", "chennai", "noida", "gurgaon", "gurugram"]),
    "pakistan": (["pakistan"], ["lahore", "karachi", "islamabad", "rawalpindi", "faisalabad", "peshawar", "multan"]),
    "egypt": (["egypt"], ["cairo"]),
    "nigeria": (["nigeria"], ["lagos", "abuja"]),
    "kenya": (["kenya"], ["nairobi"]),
    "south africa": (["south africa"], ["cape town", "johannesburg"]),
    "brazil": (["brazil", "brasil"], ["sao paulo", "são paulo", "rio de janeiro"]),
    "mexico": (["mexico"], ["mexico city", "guadalajara"]),
    "japan": (["japan"], ["tokyo", "osaka"]),
    "malaysia": (["malaysia"], ["kuala lumpur"]),
    "philippines": (["philippines"], ["manila"]),
    "turkey": (["turkey", "türkiye", "turkiye"], ["istanbul", "ankara"]),
}
REMOTE_ALIASES = ["remote", "work from home", "wfh", "fully remote", "remote-first"]
ANYWHERE_ALIASES = ["anywhere", "worldwide", "any location", "global"]
OTHER_KNOWN = ["europe", "emea", "apac", "latam", "middle east"]

LEAD_COLUMNS = ["Date Added", "Mode", "Company", "Job Title", "Location", "Employment Type", "Posted",
                "Posting Window", "Date Source", "Source", "Job URL", "Verification", "Fit Score", "Why It Fits",
                "Relevant Skills", "Pitch / Tip", "Contact", "Email", "Contact Source", "Apply Via",
                "Application Status", "Outreach Status", "Gmail Status", "Next Step", "Run ID"]
CONTACT_COLUMNS = ["Company", "Name", "Role", "Email", "Type", "Source URL", "Verification", "Associated Job",
                   "Outreach Status", "Run ID"]
APPLICATION_COLUMNS = ["Date", "Company", "Job Title", "Job URL", "Apply Via", "Application Status", "Cover Letter",
                       "Application Answers", "Outreach To", "Outreach Subject", "Outreach Body", "Gmail Status",
                       "Next Action", "Run ID"]
RUNLOG_COLUMNS = ["Run ID", "Date", "Time", "Run By", "Mode", "Roles", "Locations", "Posting Window", "Undated Jobs",
                  "Platforms", "Agents Used", "Ranking", "Min Score", "Target", "Saved", "Saved By Source", "Searches",
                  "Candidates Reviewed", "Page Checked", "Rejected (reasons)", "Duplicates", "Outside Window", "No Date",
                  "Contacts Verified", "Contacts Unverified", "Gmail Drafts", "Gmail Sent", "Gmail Failed", "Applied",
                  "Needs You", "Status", "Errors / Limitations"]
EXCLUDED_COLUMNS = ["Run ID", "Title / Company", "URL", "Reason", "Detail"]
# older Jword files used these names; they are renamed on import so repeated runs keep their history
OLD_NAMES = {"Status": "Application Status", "Contact Link": "Contact Source", "Contact LinkedIn": "Contact Source",
             "Job Board": "Source", "Found On": "Source URL", "Cover Letter / Message": "Cover Letter",
             "Answers Used": "Application Answers", "Posted Within": "Posting Window", "Notes": "Errors / Limitations"}
EMAIL_MODES = {"contacts_only": "Find contacts only", "chat": "Prepare emails in chat",
               "drafts": "Create Gmail drafts", "approve_each": "Send each after approval",
               "auto": "Capped automatic sending (job applications only)"}
SUBMIT_MODES = {"ask_each": "Ask before each submit", "auto_profile": "Submit when every answer is in the profile",
                "fill_only": "Fill forms, user submits"}
AUTO_SEND_CAP = 10
OUTREACH_STATUSES = {"prepared": "Prepared", "draft": "Draft created", "sent": "Sent", "failed": "Failed",
                     "skipped": "Skipped"}
PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{2,40}\]|\{\{|\}\}|<[A-Z][A-Za-z ]{2,30}>|\bYOUR (NAME|COMPANY)\b|\bXXX+\b|lorem ipsum", re.I)
OPT_OUT_RE = re.compile(r"not (a fit|interested|relevant)|opt.?out|unsubscribe|rather not hear|won'?t follow up|reply .?stop|let me know .{0,40}(stop|not)", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# Sample addresses job boards show as teasers (live test: jobgether's "m.rivera@company.com", "unlocked after you apply")
PLACEHOLDER_DOMAINS = {"company.com", "example.com", "example.org", "domain.com", "email.com", "yourcompany.com",
                       "companyname.com", "test.com", "sample.com"}
FREEMAIL = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "hotmail.com", "outlook.com", "live.com",
            "icloud.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "yandex.com", "msn.com"}
GENERIC_LOCAL = {"careers", "career", "jobs", "job", "hr", "recruiting", "recruitment", "talent", "hiring", "people",
                 "apply", "applications", "hello", "info", "contact", "team", "work", "joinus", "join", "office",
                 "enquiries", "inquiries", "sales", "partnerships", "business", "hi"}
NOREPLY = re.compile(r"^(no-?reply|do-?not-?reply|bounce|mailer-daemon|postmaster)", re.I)
ATS = {"greenhouse.io": "Greenhouse form", "lever.co": "Lever form", "ashbyhq.com": "Ashby form",
       "workable.com": "Workable form", "smartrecruiters.com": "SmartRecruiters form", "recruitee.com": "Recruitee form",
       "teamtailor.com": "Teamtailor form", "bamboohr.com": "BambooHR form", "personio.de": "Personio form",
       "personio.com": "Personio form", "breezy.hr": "Breezy form", "jazzhr.com": "JazzHR form",
       "applytojob.com": "JazzHR form", "myworkdayjobs.com": "Workday form", "icims.com": "iCIMS form",
       "wellfound.com": "Wellfound (login)"}
NO_AUTOMATION = {"linkedin.com": "LinkedIn", "indeed.com": "Indeed", "glassdoor.com": "Glassdoor",
                 "glassdoor.co.uk": "Glassdoor", "ziprecruiter.com": "ZipRecruiter", "ziprecruiter.co.uk": "ZipRecruiter"}
JOB_STATUSES = {"to_apply": "To apply", "prepared": "Prepared", "applied": "Applied", "needs_you": "Needs you",
                "draft_ready": "Draft ready", "emailed": "Emailed", "skipped": "Skipped", "failed": "Failed", "new": "New"}
PROFILE_REQUIRED = ["full_name", "email", "phone", "location", "work_authorization", "needs_sponsorship",
                    "notice_period", "salary_expectation"]

REVIEW_BATCH = 6       # candidates handed to Claude per review step
MAX_TARGET = 25
IN_FLIGHT = ("needs_open_check", "needs_contact")

STOP = set(("and the for with from that this are you your our will have has who into able years year "
            "experience work working team teams strong good great skills skill job role looking want based "
            "plus etc also using use well can all any new more other per about over developer engineer "
            "senior junior lead").split())

# ============================================================================ helpers


_CAPTURE = None


def out(obj):
    if _CAPTURE is not None:
        _CAPTURE.append(obj)
        return
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def with_next(args, result: dict):
    """Print `result` plus what `next` says, so Claude needs one command per step instead of two."""
    global _CAPTURE
    _CAPTURE = []
    try:
        cmd_next(args)
    finally:
        nxt, _CAPTURE = (_CAPTURE[0] if _CAPTURE else {}), None
    result.pop("next", None)
    result["next_action"] = nxt
    out(result)


def fail(msg):
    out({"error": msg})
    sys.exit(1)


def split_list(value: str, slash: bool = False) -> list[str]:
    if not value:
        return []
    pattern = r"\s*[,;/|]\s*" if slash else r"\s*[,;|]\s*|\s+OR\s+"
    res, seen = [], set()
    for x in (re.sub(r"\s+", " ", x).strip() for x in re.split(pattern, value)):
        if x and x.lower() not in seen:
            seen.add(x.lower())
            res.append(x)
    return res


def words(s: str) -> list[str]:
    toks = [w.rstrip(".") for w in re.split(r"[^a-z0-9+#.]+", str(s or "").lower())]
    return [w for w in toks if len(w) >= 3 and w not in STOP]


ROLE_SYNONYMS = {"ai": r"(?:ai|artificial intelligence|genai|gen ai)", "ml": r"(?:ml|machine learning)",
                 "js": r"(?:js|javascript)", "ui": r"(?:ui|user interface)", "ux": r"(?:ux|user experience)"}


def role_matchers(roles) -> list:
    """Patterns that recognise a role in a title/snippet even when written differently:
    'AI Engineer' also matches 'AI/ML Engineer', 'AI & ML Engineer', 'Artificial Intelligence Engineer'."""
    pats = []
    for r in roles:
        toks = re.findall(r"[a-z0-9+#]+", str(r).lower())
        if not toks:
            continue
        alts = [ROLE_SYNONYMS.get(t, re.escape(t)) + r"(?![a-z0-9])" for t in toks]
        gap = r"(?:[^a-z0-9.]|(?<![a-z0-9])[a-z0-9]{1,12}[^a-z0-9.]){0,5}?"
        pats.append(re.compile(r"(?<![a-z0-9])" + gap.join(alts)))
        pats.extend(re.compile(r"(?<![a-z0-9])" + re.escape(w)) for w in words(r))   # distinctive words: 'flutter'
    return pats


def dedupe_slug(s: str) -> str:
    s = re.sub(r"\b(pvt|private|ltd|limited|inc|llc|co|company|corp|plc|gmbh)\b\.?", "", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def dedupe_key(mode: str, company: str, role: str) -> str:
    return f"{mode}|{dedupe_slug(company)}|{dedupe_slug(role)}" if company and role else ""


def normalize_job_url(raw: str) -> str:
    """Canonical job URL: lower-case host without www, tracking params dropped, no trailing slash."""
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        u = urlparse(s)
        host = (u.hostname or "").lower()
    except ValueError:
        host = ""
    if not host:
        return s.lower().split("#")[0].rstrip("/")
    host = re.sub(r"^www\.", "", host)
    q = parse_qs(u.query)
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        m = re.search(r"/jobs/view/(?:[^/]*?-)?(\d{6,})", u.path)
        if m:
            return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    if host == "indeed.com" or host.endswith(".indeed.com"):
        jk = (q.get("jk") or q.get("vjk") or [None])[0]
        if jk:
            return f"https://www.indeed.com/viewjob?jk={jk}"
    keep = sorted((k, v) for k, vs in q.items() if not TRACKING_PARAMS.match(k) for v in vs)
    query = ("?" + "&".join(f"{k}={v}" for k, v in keep)) if keep else ""
    return f"https://{host}{u.path.rstrip('/') or ('/' if query else '')}{query}"


def display_url(raw: str) -> str:
    """The link shown to the user: original host and path, tracking parameters removed."""
    s = str(raw or "").strip()
    try:
        u = urlparse(s)
    except ValueError:
        return s
    if not u.scheme or not u.netloc:
        return s
    keep = [(k, v) for k, vs in parse_qs(u.query, keep_blank_values=True).items() if not TRACKING_PARAMS.match(k) for v in vs]
    query = ("?" + "&".join(f"{k}={v}" for k, v in keep)) if keep else ""
    return f"{u.scheme}://{u.netloc}{u.path or '/'}{query}"


def domain_of(url: str) -> str:
    try:
        host = re.sub(r"^www\.", "", (urlparse(url).hostname or "").lower())
    except ValueError:
        return ""
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def source_of(url: str) -> str:
    d = domain_of(url)
    return SOURCE_NAMES.get(d, d)


def is_listing(title: str, url: str) -> bool:
    u = urlparse(url)
    path_q = u.path + (("?" + u.query) if u.query else "")
    return bool(LISTING_URL.search(path_q)) or any(p.search(title or "") for p in LISTING_TITLE)


DATE_RX = (r"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?"
           r"([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{1,2}(?:st|nd|rd|th)? [A-Z][a-z]{2,8},? \d{4}"
           r"|\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4})")


def parse_date(txt: str):
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(txt or "")).replace(",", " ")
    t = re.sub(r"\s+", " ", re.sub(r"(?<=[A-Za-z])\.", "", t)).strip()
    for fmt in ("%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- posting-date window (strict)
# The user picks how recently jobs must have been posted. The window is a hard rule: a job is kept only
# when its ORIGINAL posting date is known to fall inside it. "Updated / reposted / reviewed" dates are not
# posting dates; they only prove the job is at least that old (so they can rule a job out, never in).

UPDATED_WORDS = re.compile(r"(updated|reposted|re-posted|refreshed|reviewed|modified|edited|bumped|renewed|active|last seen)\W*$", re.I)
UNIT_ALIASES = {"m": "minute", "min": "minute", "mins": "minute", "h": "hour", "hr": "hour", "hrs": "hour", "d": "day",
                "w": "week", "wk": "week", "wks": "week", "mo": "month", "mos": "month", "y": "year", "yr": "year"}
POSTED_LABELS = r"(?:first seen|first indexed|date posted|posted on|posted|published on|published|listed on|listed|created|opened|date|reposted|re-posted|updated|last updated|reviewed|refreshed|modified)"
WINDOW_PRESETS = {"24h": 1, "1d": 1, "day": 1, "today": 0, "3d": 3, "7d": 7, "week": 7, "14d": 14,
                  "30d": 30, "month": 30, "60d": 60}
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def today_of(st=None) -> dt.date:
    """The run's reference day (fixed at init so a run is judged consistently)."""
    if st and st.get("config", {}).get("run_date"):
        return dt.date.fromisoformat(st["config"]["run_date"])
    return dt.date.today()


def parse_loose_date(txt: str, today: dt.date):
    """'2026-11-01', 'Nov 1', 'November 1 2026', '1 Nov', '01/11/2026' -> date (year defaults to the latest past one)."""
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(txt or "").strip().lower()).replace(",", " ")
    t = re.sub(r"\s+", " ", t).strip(" .")
    d = parse_date(t.title())
    if d:
        return d.date()
    m = re.fullmatch(r"([a-z]{3})[a-z]*\.? (\d{1,2})|(\d{1,2}) ([a-z]{3})[a-z]*\.?", t)
    if m:
        mon = (m.group(1) or m.group(4))[:3]
        day = int(m.group(2) or m.group(3))
        if mon in MONTHS:
            try:
                d = dt.date(today.year, MONTHS.index(mon) + 1, day)
            except ValueError:
                return None
            return d if d <= today else d.replace(year=today.year - 1)
    return None


def parse_window(spec: str, today: dt.date) -> dict | None:
    """User's 'posted within' answer -> {label, start, end} (ISO dates, inclusive), or None for 'any time'.
    Accepts: 24h, 3d, 7d, 14d, 30d, 60d, 'last 10 days', '2 weeks', 'this week', 'this month', 'today',
    '2026-11-01..2026-11-10', 'between November 1 and November 10', 'from Nov 1 to Nov 10', 'since Nov 3'."""
    s = re.sub(r"\s+", " ", str(spec or "").strip().lower())
    s = re.sub(r"^(jobs )?(posted )?(with)?in (the )?|^(the )?(last|past) ", "", s).strip()
    s = re.sub(r"^(last|past) ", "", s).strip()
    if s in ("", "any", "any time", "anytime", "all"):
        return None
    days = None
    if s in WINDOW_PRESETS:
        days = WINDOW_PRESETS[s]
    m = re.fullmatch(r"(\d+)\s*(h|hr|hrs|hours?|d|days?|w|wks?|weeks?|m|mo|months?)", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        days = max(1, math.ceil(n / 24)) if u.startswith("h") else n * 7 if u.startswith("w") else n * 30 if u.startswith("m") else n
    if s in ("this week", "current week"):
        start = today - dt.timedelta(days=today.weekday())
        return {"label": f"This week ({start.isoformat()} to {today.isoformat()})", "start": start.isoformat(), "end": today.isoformat()}
    if s in ("this month", "current month"):
        start = today.replace(day=1)
        return {"label": f"This month ({start.isoformat()} to {today.isoformat()})", "start": start.isoformat(), "end": today.isoformat()}
    if days is not None:
        start = today - dt.timedelta(days=days)
        label = "Today" if days == 0 else "Last 24 hours" if days == 1 else f"Last {days} days"
        return {"label": f"{label} ({start.isoformat()} to {today.isoformat()})", "start": start.isoformat(), "end": today.isoformat()}
    m = re.fullmatch(r"(?:since|after|from) (.+)", s)
    if m and not re.search(r" (to|until|and|-) ", m.group(1)):
        a = parse_loose_date(m.group(1), today)
        if a:
            return {"label": f"{a.isoformat()} to {today.isoformat()}", "start": a.isoformat(), "end": today.isoformat()}
    m = (re.fullmatch(r"(?:between |from )?(.+?)\s*(?:\.\.| to | until | and | - | – )\s*(.+)", s))
    if m:
        a, b = parse_loose_date(m.group(1), today), parse_loose_date(m.group(2), today)
        if a and b:
            if a > b:
                a, b = b, a
            b = min(b, today)
            return {"label": f"{a.isoformat()} to {b.isoformat()}", "start": a.isoformat(), "end": b.isoformat()}
    fail(f"Could not understand the posting window '{spec}'. Use e.g. 24h, 3d, 7d, 14d, 30d, 60d, "
         "'last 10 days', 'this week', or a range like 2026-11-01..2026-11-10.")


SIDEBAR_RE = re.compile(r"\b(similar|related|other|more|recommended|recent|latest)\s+(remote\s+)?(jobs|positions|openings|roles|job titles)\b"
                        r"|\bsimilar openings at\b|\bview all\b.{0,20}\bjobs\b"
                        r"|\bjobs you may like\b|\bpeople also viewed\b|\bexplore related\b", re.I)


def main_text(text: str) -> str:
    """Drop 'Similar jobs' / 'Related jobs' sidebars: their dates belong to other postings (live test)."""
    t = str(text or "")
    m = SIDEBAR_RE.search(t)
    return t[:m.start()] if m and m.start() > 0 else t


def estimate_posting(text: str, today: dt.date | None = None, assume_posted: bool = False):
    """Find a posting date in text. Returns {min, max (days ago; max None = unbounded), text, kind} or None.
    kind = 'posted' (original posting date) or 'updated' (reposted / updated / reviewed date)."""
    t = main_text(text)
    today = today or dt.date.today()
    found = []

    def kind_at(pos, label=""):
        before = t[max(0, pos - 22):pos]
        # "first seen" (when a board first indexed it) also only bounds the original date: posted on/before it
        if re.search(r"updated|reposted|re-posted|refreshed|reviewed|modified|edited|renewed|first seen|first indexed", label, re.I) or UPDATED_WORDS.search(before.strip()):
            return "updated"
        return "posted"

    m = re.search(r'"datePosted"\s*:\s*"(\d{4}-\d{2}-\d{2})', t)
    if m:
        d = dt.date.fromisoformat(m.group(1))
        found.append((-1, {"min": (today - d).days, "max": (today - d).days, "text": m.group(1), "kind": "posted"}))
    rel = (r"\b(\d+|an?|one)(\+)?\s*(minutes?|mins?|hours?|hrs?|days?|weeks?|wks?|months?|mos?|years?|yrs?|m|h|d|w|mo|y)\b"
           r"(?:,?\s*(?:and\s+)?\d+\s*(?:minutes?|mins?|hours?|hrs?|days?|h|m|d))?\s+ago\b")
    for m in re.finditer(rel, t, re.I):
        n = 1 if m.group(1).lower() in ("a", "an", "one") else int(m.group(1))
        plus, unit = m.group(2), m.group(3).lower()
        unit = UNIT_ALIASES.get(unit, UNIT_ALIASES.get(unit.rstrip("s"), unit))
        if unit.startswith(("minute", "min")):
            lo, hi = 0, 0
        elif unit.startswith(("hour", "hr")):
            lo, hi = (0, 1) if n >= 12 else (0, 0)
        elif unit.startswith("day"):
            lo, hi = n, n
        elif unit.startswith(("week", "wk")):
            lo, hi = n * 7, n * 7 + 6
        elif unit.startswith(("month", "mo")):
            lo, hi = n * 28, n * 30 + 29
        else:
            lo, hi = n * 365, None
        if plus:
            hi = None
        found.append((m.start(), {"min": lo, "max": hi, "text": m.group(0), "kind": kind_at(m.start())}))
    for m in re.finditer(r"\b(just now|just posted|posted today|today|new today)\b", t, re.I):
        found.append((m.start(), {"min": 0, "max": 0, "text": m.group(0), "kind": kind_at(m.start())}))
    for m in re.finditer(r"\b(\d{1,2})(h|d|w|mo)\s*[•·]", t):          # LinkedIn post age: "2d •", "1w ·"
        n, u = int(m.group(1)), m.group(2)
        lo, hi = {"h": (0, 1), "d": (n, n), "w": (n * 7, n * 7 + 6), "mo": (n * 28, n * 30 + 29)}[u]
        found.append((m.start(), {"min": lo, "max": hi, "text": m.group(0).strip(" •·"), "kind": "posted"}))
    for m in re.finditer(r"\b(?:posted\s+)?(last|this|a)\s+(week|month|year)\b(?!\s+(?:to|until))", t, re.I):
        rel_, unit = m.group(1).lower(), m.group(2).lower()
        if rel_ == "this":
            lo, hi = 0, {"week": 6, "month": 30, "year": 365}[unit]
        else:                                        # "last week", "a month ago"-style vague wording
            lo, hi = {"week": (7, 13), "month": (28, 60), "year": (365, None)}[unit]
        if not re.search(r"ago|posted", t[m.start():m.end() + 4], re.I) and rel_ == "a":
            continue
        found.append((m.start(), {"min": lo, "max": hi, "text": m.group(0), "kind": kind_at(m.start())}))
    for m in re.finditer(r"\b(yesterday|yday)\b", t, re.I):
        found.append((m.start(), {"min": 1, "max": 1, "text": m.group(0), "kind": kind_at(m.start())}))
    for m in re.finditer(r"\b(" + POSTED_LABELS + r")[:\s]*(?:on\s+)?" + DATE_RX, t, re.I):
        d = parse_date(m.group(2))
        if d:
            age = (today - d.date()).days
            found.append((m.start(), {"min": age, "max": age, "text": m.group(0).strip(), "kind": kind_at(m.start(), m.group(1))}))
    if assume_posted and not found:                      # a bare date given as "the posting date"
        d = parse_loose_date(t, today)
        if d:
            found.append((0, {"min": (today - d).days, "max": (today - d).days, "text": t.strip(), "kind": "posted"}))
    if not found:
        return None
    found.sort(key=lambda x: x[0])
    posted = [f for _, f in found if f["kind"] == "posted"]
    if posted:
        return posted[0]
    return min((f for _, f in found), key=lambda f: f["min"])   # newest 'updated' date = tightest bound


def window_verdict(est, window, today: dt.date) -> str:
    """'in' (posting date proven inside the window), 'out' (proven outside) or 'unclear'."""
    if not window:
        return "in"
    if not est:
        return "unclear"
    start, end = dt.date.fromisoformat(window["start"]), dt.date.fromisoformat(window["end"])
    newest = today - dt.timedelta(days=est["min"])
    oldest = None if est["max"] is None else today - dt.timedelta(days=est["max"])
    if est["kind"] == "updated":                    # original posting is on/before this date
        return "out" if newest < start else "unclear"
    if newest < start or (oldest and oldest > end):
        return "out"
    if oldest is not None and oldest >= start and newest <= end:
        return "in"
    return "unclear"


def posted_label(est, today: dt.date) -> str:
    """'2026-11-12' or '2026-11-01 to 2026-11-07' (estimated from '1 week ago')."""
    if not est or est["kind"] != "posted":
        return ""
    newest = today - dt.timedelta(days=est["min"])
    if est["max"] is None:
        return f"on/before {newest.isoformat()}"
    oldest = today - dt.timedelta(days=est["max"])
    return newest.isoformat() if oldest == newest else f"{oldest.isoformat()} to {newest.isoformat()}"


def parse_age(text: str):
    """(days, text) for the newest date found. Kept for older callers/tests."""
    est = estimate_posting(text)
    return (est["min"], est["text"]) if est else None


def closing_passed(text: str) -> bool:
    """True if the text shows a closing/expiry date that is already in the past."""
    m = re.search(r"\b(?:closes|closing date|closing|expires|expiry date|apply by|apply before|deadline|"
                  r"accepted until|applications close[sd]?|open until)[:\s]*(?:on\s+)?" + DATE_RX,
                  str(text or ""), re.I)
    d = parse_date(m.group(1)) if m else None
    return bool(d and d.date() < dt.date.today())


def parse_title(title: str, url: str) -> dict:
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    t = re.sub(r"\s*[|\-–—]\s*(LinkedIn|Indeed(\.com)?|Rozee\.pk|Bayt\.com|Greenhouse|Lever|Wellfound|Built In)\s*$", "", t, flags=re.I)
    t = re.sub(r"\s*(\.\.\.|…)\s*$", "", t)
    company = role = loc = ""
    if m := re.match(r"^(.+?) hiring (.+?) in (.+)$", t, re.I):
        company, role, loc = m.groups()
    elif m := re.match(r"^Job Application for (.+?) at (.+)$", t, re.I):
        role, company = m.groups()
    elif m := re.match(r"^(.+?) jobs? in (.+?) at (.+)$", t, re.I):
        role, loc, company = m.groups()
    elif m := re.match(r"^(.+?) at (.+)$", t, re.I):
        role, company = m.groups()
    else:
        parts = [p.strip() for p in re.split(r"\s+[|\-–—]\s+", t) if p.strip()]
        if re.search(r"jobs\.lever\.co", url, re.I):
            company, role = (parts + ["", ""])[:2]
        else:
            role, company, loc = (parts + ["", "", ""])[:3]
    if not company:
        m = re.search(r"greenhouse\.io/([^/]+)/jobs", url, re.I) or re.search(r"jobs\.lever\.co/([^/]+)", url, re.I) \
            or re.search(r"https?://([^./]+)\.(recruitee|teamtailor|workable|bamboohr|personio)\.", url, re.I)
        if m:
            company = re.sub(r"[-_]+", " ", m.group(1))
    return {"company": company.strip(), "role": role.strip(), "location": loc.strip()}


class LocationMatcher:
    """'match' = in a picked location, 'other' = clearly somewhere else, 'unknown' = can't tell."""

    def __init__(self, locations: list[str]):
        self.anywhere = any(l.lower() in ANYWHERE_ALIASES for l in locations)
        self.selected = [(l, self._terms(l)) for l in locations]
        parent = set()
        for l in locations:
            g = self._group(l)
            if g and g[0] == "city":
                parent.update(LOCATION_GROUPS[g[1]][0])
        sel_terms = {t for _, ts in self.selected for t in ts}
        known = [a for al, cities in LOCATION_GROUPS.values() for a in al + cities] + OTHER_KNOWN
        self.other = [a for a in known if a not in sel_terms and a not in parent]

    @staticmethod
    def _group(name: str):
        k = name.lower()
        for g, (aliases, cities) in LOCATION_GROUPS.items():
            if k == g or k in aliases:
                return ("country", g)
            if k in cities:
                return ("city", g)
        return None

    def _terms(self, loc: str) -> list[str]:
        k = loc.lower()
        if k in REMOTE_ALIASES or "remote" in k:
            return REMOTE_ALIASES
        g = self._group(k)
        if g and g[0] == "country":
            aliases, cities = LOCATION_GROUPS[g[1]]
            return aliases + cities
        return [k]

    @staticmethod
    def _has(text: str, term: str) -> bool:
        return re.search(rf"(^|[^a-z]){re.escape(term)}([^a-z]|$)", text, re.I) is not None

    def match(self, text: str):
        if self.anywhere:
            return "match", "Anywhere"
        t = str(text or "").lower()
        if not t.strip():
            return "unknown", ""
        for label, terms in self.selected:
            if any(self._has(t, w) for w in terms):
                return "match", label
        for w in self.other:
            if self._has(t, w):
                return "other", w
        return "unknown", ""


def keyword_score(cfg: dict, title: str, snippet: str, location: str, matcher: LocationMatcher):
    title_l = str(title or "").lower()
    text = f"{title_l} {str(snippet or '').lower()}"
    role_pts, note = 0, "no role match"
    roles = [r.lower() for r in cfg["roles"]]
    if any(r in title_l for r in roles):
        role_pts, note = 2, "role matches title"
    elif any(any(w in title_l for w in words(r)) for r in roles) or any(r in text for r in roles):
        role_pts, note = 1, "role partly matches"
    loc_words = {w for _, ts in matcher.selected for t in ts for w in words(t)}
    offer_terms = [t for t in dict.fromkeys(words(cfg.get("offer", ""))) if t not in loc_words]
    hits = [t for t in offer_terms if t in text]
    skill_pts = 2 if len(hits) >= 3 else 1 if hits else 0
    status, loc = matcher.match(f"{location} {text}")
    loc_pts = 1 if status == "match" else 0
    score = min(5, 1 + role_pts + skill_pts + loc_pts)
    reason = f"{note}; {len(hits)} skill match(es)" + (f" ({', '.join(hits[:5])})" if hits else "") + \
        (f"; location matches ({loc})" if loc_pts else "")
    return score, reason, status, loc


def emails_in(text: str) -> list[str]:
    seen, res = set(), []
    for e in EMAIL_RE.findall(str(text or "")):
        e = e.strip(".").lower()
        if e not in seen and not NOREPLY.match(e) and not re.search(r"\.(png|jpe?g|gif|webp|svg)$", e):
            seen.add(e)
            res.append(e)
    return res


def email_type(email: str) -> str:
    local = email.split("@")[0].lower()
    parts = [x for x in re.split(r"[-._+0-9]+", local) if x]
    return "Generic" if local in GENERIC_LOCAL or any(x in GENERIC_LOCAL for x in parts) else "Named"


def apply_via(c: dict) -> str:
    """How this job is applied for (decides whether Claude may fill the form)."""
    d = domain_of(c["url"])
    if d == "linkedin.com" and "/jobs/" not in c["url"] and any(e.get("source") == c["url"] for e in c.get("emails", [])):
        return "Email (from LinkedIn hiring post)"
    if d in NO_AUTOMATION:
        return f"{NO_AUTOMATION[d]} (apply yourself)"
    if d in ATS:
        return ATS[d]
    if any(e["source"] == c["url"] for e in c.get("emails", [])) and re.search(r"\b(send|email) (your )?(cv|resume|application)", c.get("snippet", ""), re.I):
        return "Email"
    if not looks_like_company_site(c, d) and c.get("source"):
        return f"Via {c['source']} listing"           # a job board, not the employer's own site
    return "Company site"


def add_email(c: dict, email: str, source: str, name="", role="", from_posting=False) -> str:
    """Add one email to a lead. Returns '' if added, else the reason it was refused."""
    email = str(email or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return "not a valid email"
    if NOREPLY.match(email):
        return "no-reply address"
    if email.split("@")[1] in PLACEHOLDER_DOMAINS:
        return "placeholder/sample address"
    if email.split("@")[1] in FREEMAIL and not from_posting:
        return "personal mailbox (only accepted when the job posting itself lists it)"
    if any(e["email"] == email for e in c.setdefault("emails", [])):
        return "already recorded"
    typ = email_type(email)
    nm = str(name or "").strip()
    c["emails"].append({"email": email, "name": nm, "role": str(role or "").strip(),
                        "type": typ if (typ == "Generic" or nm) else "Named (identity unconfirmed)",
                        "source": source, "verification": email_verification(c, email, source, from_posting)})
    return ""


def best_email(c: dict) -> str:
    em = c.get("emails") or []
    if not em:
        return ""
    em = [e for e in em if e.get("email") and is_sendable(e)] or [e for e in em if e.get("email")]
    if not em:
        return ""
    rank = lambda e: (0 if e["type"].startswith("Named") and re.search(r"recruit|talent|hr|people|hiring", e["role"] or "", re.I)
                      else 1 if e["type"] == "Generic" and re.match(r"(careers?|jobs?|hr|recruit|talent|hiring|people|apply)", e["email"])
                      else 2 if e["type"].startswith("Named") else 3)
    return sorted(em, key=rank)[0]["email"]


def looks_like_company_site(c: dict, domain: str) -> bool:
    """True if the domain plausibly belongs to the company (a name token appears in it).
    Stops job boards (taraki.co, dailyremote.com, qureos.com) being taken for the employer's site."""
    d = re.sub(r"[^a-z0-9]", "", (domain or "").split(".")[0].lower())
    toks = [t for t in re.findall(r"[a-z0-9]+", (c.get("company") or "").lower())
            if len(t) >= 3 and t not in ("the", "inc", "ltd", "llc", "pvt", "private", "limited", "technologies", "tech",
                                         "solutions", "software", "group", "company", "labs", "client", "named", "not")]
    joined = re.sub(r"[^a-z0-9]", "", (c.get("company") or "").lower())
    return bool(d) and (any(t in d for t in toks) or (len(joined) >= 4 and joined[:12] in d))


def email_verification(c: dict, email: str, source: str, from_posting: bool) -> str:
    """Where the address was published decides how far it can be trusted (and whether it may be emailed)."""
    edom = email.split("@")[-1].lower()
    sdom = domain_of(source)
    site = (c.get("website") or "").lower()
    if from_posting:
        return "Verified: in the job post"
    if sdom in ATS:                     # the company's own ATS page (Greenhouse, Lever, ...)
        return "Verified: company ATS page"
    if sdom and (sdom == edom or sdom.endswith("." + edom) or edom.endswith("." + sdom)):
        return "Verified: company website"
    if site and (sdom == site or sdom.endswith("." + site)):      # published on the company's own site
        return "Verified: company website"
    if sdom in ATS:                     # the company's own ATS page (Greenhouse, Lever, ...) for this job
        return "Verified: company ATS page"
    return "Unverified: third-party page"


def is_sendable(e: dict) -> bool:
    return str(e.get("verification", "Verified")).startswith("Verified") and bool(e.get("email"))


def is_anywhere(s: str) -> bool:
    return not s or s.lower() in ANYWHERE_ALIASES


def is_remote(s: str) -> bool:
    return bool(re.search(r"remote|work from home", s or "", re.I))


# ============================================================================ state


def load(args) -> dict:
    p = Path(args.state)
    if not p.exists():
        fail(f"No run found at {p}. Start one with: jword.py init ...")
    return json.loads(p.read_text())


def save(args, st: dict):
    p = Path(args.state)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1, ensure_ascii=False))


def read_existing(path: str) -> dict:
    """Read an earlier Jword Excel/CSV file: Leads + Run Log rows (for de-dup and appending)."""
    res = {"leads": [], "runlog": []}
    p = Path(path)
    if not p.exists():
        fail(f"Existing leads file not found: {path}")
    if p.suffix.lower() == ".csv":
        import csv
        with p.open(newline="", encoding="utf-8-sig") as f:
            res["leads"] = list(csv.DictReader(f))
        return res
    import openpyxl
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    res.update({"contacts": [], "applications": []})
    res["excluded"] = []
    for sheet, key in (("Leads", "leads"), ("Run Log", "runlog"), ("Contacts", "contacts"), ("Applications", "applications"),
                       ("Excluded", "excluded")):
        ws = wb[sheet] if sheet in wb.sheetnames else (wb.worksheets[0] if key == "leads" else None)
        if ws is None:
            continue
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = [str(h or "").strip() for h in rows[0]]
        if key == "applications":
            hdr = ["Next Action" if h == "Next Step" else h for h in hdr]
        hdr = [h if h in hdr and OLD_NAMES.get(h) in hdr else OLD_NAMES.get(h, h) for h in hdr]
        for r in rows[1:]:
            if any(v not in (None, "") for v in r):
                res[key].append({h: ("" if v is None else v) for h, v in zip(hdr, r)})
    return res


def cand(st, cid):
    return next((c for c in st["candidates"] if c["id"] == cid), None)


def known_urls(st) -> set:
    return set(st["known_urls"]) | {c.get("nurl") or normalize_job_url(c["url"]) for c in st["candidates"]}


def known_keys(st) -> set:
    keys = set(st["known_keys"])
    keys.update(c["key"] for c in st["candidates"]
                if c.get("key") and (c.get("status") in ("saved", "surplus", "ready") + IN_FLIGHT
                                     or (c.get("status") == "rejected" and c.get("outcome") in ("low_fit", "closed"))))
    return keys   # a job already judged low-fit or closed isn't re-reviewed when another board copies it


LINKEDIN_SHARE = 0.4      # LinkedIn may supply up to ~40% of the jobs (others ~33%): a priority, not a monopoly


def source_cap(st, src: str = "") -> int:
    """Most leads one website may supply, so results stay varied (lifted when nothing else is left)."""
    target = st["config"]["target"]
    base = max(2, math.ceil(target / 3))
    return max(base, math.ceil(target * LINKEDIN_SHARE)) if src == "LinkedIn" else base


def source_load(st, src) -> int:
    return sum(1 for c in st["candidates"] if c["source"] == src and c["status"] in ("saved",) + IN_FLIGHT)


# ============================================================================ outcomes


REJECT_REASONS = {"low_fit": "Low fit for the CV / offer", "duplicate": "Duplicate of a job already found",
                  "closed": "Closed, expired or filled", "wrong_location": "Outside the chosen locations",
                  "agency": "Recruitment agency / employer hidden", "not_job": "Not a job posting",
                  "outside_window": "Posted outside the chosen window", "no_date": "No verifiable posting date",
                  "paywalled": "Paywalled listing", "listing": "Search/listing page"}


def exclude(st, title, url, outcome, note=""):
    """Results dropped before they became candidates, kept for the Excluded sheet (capped)."""
    st["counts"][outcome] = st["counts"].get(outcome, 0) + 1
    ex = st.setdefault("excluded", [])
    if len(ex) < 400:
        ex.append({"title": title[:160], "url": url, "outcome": outcome, "note": note[:200]})


def miss(st, c, outcome, note=""):
    c["status"], c["outcome"] = "rejected", outcome
    if note:
        c["note"] = note
    st["counts"][outcome] = st["counts"].get(outcome, 0) + 1
    st["consecutive_misses"] += 1


def qualify_or_reject(st, c, score, reason, angle=""):
    cfg = st["config"]
    c["fit_score"], c["fit_reason"], c["angle"] = score, reason, angle
    if cfg["ranking"] != "none" and score is not None and score < cfg["min_score"]:
        miss(st, c, "low_fit")
        return
    c["status"] = "ready"           # promote() releases it to checks / saving, keeping sources varied


def route(st, c):
    """Qualified lead: page check -> contact lookup -> save."""
    cfg = st["config"]
    if cfg["verify_open"] and c.get("open_check") is None and "linkedin.com" not in c["url"]:
        c["status"] = "needs_open_check"
        return
    if c.get("open_check") is None:
        c["open_check"] = ("Snippet only (LinkedIn pages aren't opened)" if "linkedin.com" in c["url"]
                           else "Snippet only") if cfg["verify_open"] else "Not checked"
    if not date_gate(st, c):
        return
    if cfg["mode"] == "clients" and cfg["agencies"] == "skip" and not str(c.get("company") or "").strip():
        miss(st, c, "agency", "employer not named")      # a client lead needs a named company
        return
    if cfg["mode"] == "clients" and cfg["find_contacts"] and c.get("company") and c.get("contact") is None:
        c["status"] = "needs_contact"
        return
    save_lead(st, c)


def date_gate(st, c) -> bool:
    """Strict posting window: True if the job may be saved. Undated jobs are dropped, or parked in a
    separate 'undated' list when the user allowed that. Never relaxed to reach the target."""
    cfg = st["config"]
    if not cfg.get("window"):
        return True
    v = c.get("date_verdict") or "unclear"
    if v == "in":
        return True
    if v == "out":
        miss(st, c, "outside_window", c.get("posted") or "")
        return False
    if cfg.get("undated") == "separate":
        c["status"] = "undated"
        c["saved_at"] = dt.datetime.now().isoformat(timespec="seconds")
        return False
    miss(st, c, "no_date", "no original posting date on the listing" + (f" (only: {c['posted']})" if c.get("posted") else ""))
    return False


def set_date(st, c, est, source):
    """Record the posting-date evidence on a candidate."""
    today = today_of(st)
    c["date_est"] = est
    c["date_verdict"] = window_verdict(est, st["config"].get("window"), today)
    c["posted"] = est["text"] if est else ""
    c["posted_date"] = posted_label(est, today)
    c["date_source"] = source if est else ""
    if est and est["kind"] == "updated":
        c["date_source"] = f"{source} (updated/reposted date only)"


def save_lead(st, c):
    if st["saved"] >= st["config"]["target"]:
        c["status"] = "surplus"
        return
    c["status"] = "saved"
    c["saved_at"] = dt.datetime.now().isoformat(timespec="seconds")
    st["saved"] += 1
    st["saved_by_source"][c["source"]] = st["saved_by_source"].get(c["source"], 0) + 1
    st["consecutive_misses"] = 0
    st["dry_searches"] = 0


def promote(st, final=False):
    """Release qualified ('ready') leads, best score first, within the per-source cap
    (final=True ignores the cap so the target can still be met when sources are scarce)."""
    target = st["config"]["target"]
    while True:
        busy = sum(1 for c in st["candidates"] if c["status"] in IN_FLIGHT)
        if st["saved"] + busy >= target:
            return
        ready = [c for c in st["candidates"] if c["status"] == "ready"]
        pick = [c for c in ready if final or source_load(st, c["source"]) < source_cap(st, c["source"])]
        if not pick:
            return
        c = max(pick, key=lambda c: ((c.get("fit_score") or 0), -source_load(st, c["source"])))
        route(st, c)


# ============================================================================ commands


def cmd_init(args):
    roles = split_list(args.roles)
    locations = split_list(args.locations, slash=True)
    if not roles:
        fail("At least one role is required (--roles).")
    if not locations:
        fail("At least one location is required (--locations). Use 'Anywhere' for no location.")
    target = int(args.target)
    if not 1 <= target <= MAX_TARGET:
        fail(f"--target must be between 1 and {MAX_TARGET}.")
    agencies = args.agencies or ("skip" if args.mode == "clients" else "keep")
    platforms = [p for p in split_list(args.platforms) if p.lower() not in ("any", "all", "")]
    bad = [p for p in platforms if p not in PLATFORMS]
    if bad:
        fail(f"Unknown platform(s) {bad}. Choose from: {', '.join(PLATFORMS)} (or leave empty for any).")
    now = dt.datetime.now()
    today = now.date()
    if args.posted_within and args.posted and args.posted != args.posted_within:
        fail("Give the posting window once: --posted-within (e.g. 7d, 'last 10 days', 2026-11-01..2026-11-10).")
    window = parse_window(args.posted_within or args.posted or "7d", today)
    st = {
        "version": 3,
        "run_id": "jw-" + now.strftime("%Y%m%d-%H%M%S"),
        "started_at": now.isoformat(timespec="seconds"),
        "config": {
            "mode": args.mode, "roles": roles, "locations": locations, "offer": args.offer or "",
            "ranking": args.ranking, "min_score": int(args.min_score), "posted": window["label"] if window else "Any time",
            "window": window, "run_date": today.isoformat(), "undated": args.undated,
            "verify_open": args.verify_open == "yes", "find_contacts": args.find_contacts == "yes",
            "strict_location": args.location_filter == "strict", "agencies": agencies,
            "platforms": platforms, "platforms_only": bool(args.platforms_only and platforms),
            "target": target, "run_by": args.run_by or "",
            "max_searches": min(36, math.ceil(target * 2.5) + len(roles) * len(locations) + 2),
            "max_misses": max(30, target * 4),
        },
        "saved": 0, "saved_by_source": {}, "searches": 0, "query_index": 0, "consecutive_misses": 0,
        "counts": {}, "candidates": [], "pending_search": None, "status": "running", "notes": [],
        "known_urls": [], "known_keys": [], "existing": {"leads": [], "runlog": [], "contacts": [], "applications": [], "excluded": []},
    }
    if args.existing:
        ex = read_existing(args.existing)
        st["existing"] = ex
        want = "job" if args.mode == "jobs" else "cli"
        for r in ex["leads"]:
            if str(r.get("Mode", "")).strip().lower()[:3] in (want, ""):
                u = normalize_job_url(r.get("Job URL", ""))
                if u:
                    st["known_urls"].append(u)
                k = r.get("Dedupe Key") or dedupe_key(args.mode, r.get("Company", ""), r.get("Job Title", ""))
                if k:
                    st["known_keys"].append(k)
        prior = {}
        for r in ex.get("contacts", []):            # never email the same address again just because of a re-run
            stt = str(r.get("Outreach Status") or "")
            if r.get("Email") and stt in ("Sent", "Draft created"):
                prior[str(r["Email"]).lower()] = f"{stt} in run {r.get('Run ID', '?')}"
        for r in ex.get("applications", []):
            g = str(r.get("Gmail Status") or "")
            if r.get("Outreach To") and (g.startswith("Sent") or g.startswith("Draft")):
                prior.setdefault(str(r["Outreach To"]).lower(), f"{g} in run {r.get('Run ID', '?')}")
        st["prior_outreach"] = prior
        if args.recheck_previous:
            n = 0
            for i, r in enumerate(ex["leads"]):
                ver = str(r.get("Verification") or "")
                if r.get("Job URL") and not ver.startswith("Closed") and str(r.get("Application Status") or "") not in ("Applied", "Skipped"):
                    n += 1
                    st.setdefault("rechecks", []).append({"id": f"r{n}", "row": i, "url": r["Job URL"], "company": r.get("Company", ""),
                                                           "role": r.get("Job Title", ""), "result": None})
    save(args, st)
    out({"ok": True, "run_id": st["run_id"], "config": st["config"],
         "existing_leads_loaded": len(st["existing"]["leads"]),
         "next": "Run `jword.py next` to get the first step."})


def build_query(st) -> dict:
    """Next search: pick a board (n8n-style balancing), then that board's next role x location and wording."""
    cfg = st["config"]
    # global counter -> every role x location is covered in turn; then the neediest board serving it
    combos = [(r, l) for r in cfg["roles"] for l in cfg["locations"]]
    role, loc = combos[st["query_index"] % len(combos)]
    b = pick_board(st, loc)
    rnd = b["searches"] // max(1, len(combos))
    now = dt.datetime.now()
    loc_txt = "" if is_anywhere(loc) else ("remote" if is_remote(loc) else loc)
    recent = recency_phrases(cfg)[rnd % 3]
    site = b.get("site") or ""
    if b["name"] == "linkedin":
        styles = ['site:linkedin.com "hiring" "{role}" {loc}', 'site:linkedin.com "we\'re hiring" {role} {loc} send CV',
                  'site:linkedin.com {role} {loc} hiring {recent}', 'site:linkedin.com "{role}" {loc} job opening']
    elif site and b.get("dated"):            # boards that print "Posting Date: Nov 09, 2026"
        styles = ['site:{site} "{role}" {loc} {dated}', 'site:{site} {role} {loc} {dated}',
                  'site:{site} "{role}" {loc} {recent}', 'site:{site} "{role}" {loc}']
    elif site:
        styles = ['site:{site} "{role}" {loc}', 'site:{site} "{role}" {loc} {recent}', 'site:{site} {role} {loc} hiring',
                  'site:{site} {role} {loc}']
    else:
        styles = REMOTE_QUERY_STYLES if is_remote(loc) else QUERY_STYLES
    style = styles[rnd % len(styles)]
    if st.get("dry_searches", 0) >= 4:          # stuck: plainest wording, location (and date words) kept
        style = ("site:{site} {role} {loc} {dated}" if b.get("dated") else "site:{site} {role} {loc}") if site \
            else "{role} jobs {loc} {recent}"
    hints = date_hints(cfg)
    dated = hints[(rnd // 2) % len(hints)] if hints else ""
    query = style.format(role=role, loc=loc_txt, site=site, month=now.strftime("%B %Y"), year=now.year, recent=recent,
                         dated=dated)
    b["searches"] += 1
    return {"role": role, "location": loc, "board": b["name"], "board_label": b["label"],
            "query": re.sub(r"\s+", " ", query.replace('""', "")).strip()}


def on_platform(cfg, c) -> bool:
    plats = cfg.get("platforms") or []
    d = domain_of(c["url"])
    return any(PLATFORMS[p][1](c["source"], d) for p in plats)


def cmd_next(args):
    st = load(args)
    cfg = st["config"]

    def done(status, why):
        st["status"], st["pending_search"] = status, None
        save(args, st)
        out({"action": "done", "status": status, "why": why, "saved": st["saved"], "target": cfg["target"],
             "next": "Run `jword.py export --out <file>.xlsx`, then give the user the file and a short summary."})

    if st["saved"] >= cfg["target"]:
        return done("target_reached", "Target number of leads saved.")
    out_of_searches = st["searches"] >= cfg["max_searches"]
    # n8n-style: stop on the search budget, or after many searches in a row that saved nothing.
    # (Counting searches, not rejected results: one page of old listings must not end the run.)
    max_dry = cfg.get("max_dry_searches") or max(12, 2 * len(st.get("boards") or []))
    out_of_luck = st.get("dry_searches", 0) >= max_dry
    # Variety vs. cost: after a few searches, if enough qualified leads are already waiting,
    # let them through even if one website supplies more than its share.
    waiting = sum(1 for c in st["candidates"] if c["status"] in ("ready",) + IN_FLIGHT)
    enough = st["searches"] >= 4 and st["saved"] + waiting >= cfg["target"]
    promote(st, final=out_of_searches or out_of_luck or enough)
    if st["saved"] >= cfg["target"]:
        return done("target_reached", "Target number of leads saved.")

    # 1) follow-ups (page checks / contact lookups) on qualified leads
    max_tasks = max(1, int(getattr(args, "max_tasks", 5) or 5))
    follow = [c for c in st["candidates"] if c["status"] in IN_FLIGHT]
    pending_rc = [r for r in st.get("rechecks", []) if r["result"] is None]
    if not follow and pending_rc:
        save(args, st)
        return out({"action": "verify", "tasks": [{"id": r["id"], "type": "recheck", "url": r["url"], "company": r["company"],
                                                   "role": r["role"], "how": "web_fetch the URL. Reply {id, open: true|false|null}."}
                                                  for r in pending_rc[:max_tasks]],
                    "next": "These are jobs from the earlier tracker. Reply, then run `jword.py apply --updates <file>`."})
    if follow:
        tasks = []
        for c in follow[:max_tasks]:
            if c["status"] == "needs_open_check":
                tasks.append({"id": c["id"], "type": "open_check", "url": c["url"], "company": c.get("company"),
                              "role": c.get("role"),
                              "window": cfg["posted"],
                              "how": "web_fetch the URL. Reply {id, open: true|false|null, posted: '<ORIGINAL posting date as the page "
                                     "labels it, e.g. \"Posted 3 days ago\" or \"Date posted: 2026-11-10\"; empty if not shown>', "
                                     "updated: '<only an updated/reposted/reviewed date, if that is all the page shows>', "
                                     "posted_source: '<where on the page: header, JSON-LD datePosted, ...>'"
                                     + (", company: '<employer if the page names it>', fit_reason, angle (rewrite them now that "
                                        "the employer is known)" if not c.get("company") else "")
                                     + "}; if unsure add page_text with the first ~3000 characters."})
            else:
                city = c.get("matched_location") or next((l for l in cfg["locations"] if not is_remote(l) and not is_anywhere(l)), "")
                if is_remote(city) or is_anywhere(city):
                    city = ""
                company = str(c.get("company", "")).replace('"', "")
                tasks.append({"id": c["id"], "type": "contact", "company": c.get("company"),
                              "query": re.sub(r"\s+", " ", f'"{company}" {city} CTO OR "Head of Engineering" OR Founder OR "Engineering Manager" LinkedIn').strip(),
                              "how": "web_search the query. Pick ONE person whose result clearly shows their name and a "
                                     "relevant title at this company. Reply {id, contact: {name, title, url}} "
                                     "(url = their LinkedIn or company team page) or {id, contact: null}."})
        save(args, st)
        return out({"action": "verify", "tasks": tasks,
                    "next": "Do each task, write all replies into one JSON list, then run `jword.py apply --updates <file>`."})

    # 2) AI mode: candidates waiting for Claude's verdict (best keyword score first, sources mixed)
    queued = [c for c in st["candidates"] if c["status"] == "queued"]
    if queued:
        fresh = [c for c in queued if source_load(st, c["source"]) < source_cap(st, c["source"])] or queued
        fresh.sort(key=lambda c: (not on_platform(cfg, c), c["source"] != "LinkedIn", -(c.get("keyword_score") or 0)))
        batch, per_src = [], {}
        for c in fresh:                                   # at most 2 per source in one batch
            if per_src.get(c["source"], 0) < 2:
                batch.append(c)
                per_src[c["source"]] = per_src.get(c["source"], 0) + 1
            if len(batch) >= max(1, int(getattr(args, "batch", REVIEW_BATCH) or REVIEW_BATCH)):
                break
        save(args, st)
        return out({
            "action": "review",
            "instructions": "Score each candidate with references/scoring-rubric.md. Reply with a JSON list of "
                            "{id, is_job_posting, is_open, is_agency, company, role, location, employment_type, fit_score (1-5), "
                            "fit_reason, skills_matched, gaps, angle} then run `jword.py apply --updates <file>`.",
            "window": cfg["posted"],
            "mode": cfg["mode"], "offer": cfg["offer"], "roles": cfg["roles"], "locations": cfg["locations"],
            "candidates": [{"id": c["id"], "source": c["source"], "url": c["url"], "title": c["title"],
                            "snippet": c["snippet"], "posted": c.get("posted", "")} for c in batch],
        })

    if out_of_luck:
        return done("retry_limit_reached", f"{max_dry} searches in a row did not produce a lead.")
    if out_of_searches:
        return done("max_searches_reached", f"Used the search budget ({cfg['max_searches']} searches).")

    # 3) search
    plan = st.get("pending_search") or build_query(st)   # idempotent: asking twice gives the same search
    st["pending_search"] = plan
    save(args, st)
    out({"action": "search", **plan,
         "next": "web_search this exact query. Save one {title, url, snippet} per result that could be a SINGLE job "
                 "posting (skip pages listing many jobs, and paywalled sites). Keep date text exactly ('Posted 2d ago', "
                 "'5 days ago', 'Date: 6 hours ago', 'Updated ...'), company, location and any closed wording, but not "
                 "dates from 'Similar jobs' lists. Then run `jword.py ingest --results <file>`: it prints the next "
                 "action. If the search failed, ingest []."})


def cmd_ingest(args):
    st = load(args)
    cfg = st["config"]
    try:
        results = json.loads(Path(args.results).read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Could not read results JSON: {e}")
    issued = st.setdefault("issued", {})
    if isinstance(results, dict) and results and all(k in issued for k in results):   # parallel packet
        batches = list(results.items())
    else:
        if not st.get("pending_search"):
            fail("No search is pending. Run `jword.py next` first (or ingest a {query_id: [...]} packet from `shards`).")
        if isinstance(results, dict):
            results = results.get("results") or results.get("web") or results.get("data") or []
        batches = [(None, results)]
    total = {}
    issued_plan = st.get("pending_search") or {}
    plan_by_qid = {q: dict(issued.get(q) or {}) for q, _ in batches if q}
    for qid, res in batches:
        if qid:
            issued.pop(qid, None)
            st["searches"] += 1
        else:
            st["searches"] += 1
            st["query_index"] += 1
            st["pending_search"] = None
        plan = issued_plan if qid is None else plan_by_qid.get(qid, {})
        stats = ingest_batch(st, res if isinstance(res, list) else [], plan.get("board", ""))
        for k, v in stats.items():
            total[k] = total.get(k, 0) + v
    save(args, st)
    with_next(args, {"ok": True, "stats": total, "searches": len(batches), "saved": st["saved"], "target": cfg["target"]})


def ingest_batch(st, results, board: str = "") -> dict:
    cfg = st["config"]
    matcher = LocationMatcher(cfg["locations"])
    today = today_of(st)
    seen, keys = known_urls(st), known_keys(st)
    stats = {k: 0 for k in ("results", "new", "listing_or_irrelevant", "already_seen", "closed_or_stale",
                            "duplicate", "wrong_location", "agency", "low_fit", "queued_for_review", "qualified",
                            "outside_window", "paywalled")}
    stats["results"] = len(results)
    role_pats = role_matchers(cfg["roles"])

    for r in results:
        url = str(r.get("url") or r.get("link") or "").strip()
        title = str(r.get("title") or "").strip()
        snippet = re.sub(r"\s+", " ", str(r.get("snippet") or r.get("description") or "")).strip()
        text = f"{title} {snippet}"
        if (not url.startswith("http") or any(d in url.lower() for d in EXCLUDED_DOMAINS)
                or is_listing(title, url) or not any(p.search(text.lower()) for p in role_pats)):
            stats["listing_or_irrelevant"] += 1
            continue
        if domain_of(url) in PAYWALL_DOMAINS or PAYWALL_HINTS.search(text):
            stats["paywalled"] += 1                               # can't apply without paying
            exclude(st, title, url, "paywalled")
            continue
        nurl = normalize_job_url(url)
        if nurl in seen:
            stats["already_seen"] += 1
            continue
        seen.add(nurl)
        est = estimate_posting(snippet, today) or estimate_posting(title, today)
        if CLOSED_RE.search(text) or closing_passed(snippet):
            stats["closed_or_stale"] += 1
            exclude(st, title, url, "closed")
            continue
        if window_verdict(est, cfg.get("window"), today) == "out":
            stats["outside_window"] += 1
            exclude(st, title, url, "outside_window", est["text"])
            continue

        p = parse_title(title, url)
        c = {"id": f"c{len(st['candidates']) + 1}", "source": source_of(nurl), "url": display_url(url), "nurl": nurl, "title": title,
             "snippet": snippet[:700], "company": p["company"], "role": p["role"], "location": p["location"],
             "posted": "", "status": "new", "open_check": None, "contact": None}
        set_date(st, c, est, "search snippet")
        c["key"] = dedupe_key(cfg["mode"], c["company"], c["role"])
        if cfg.get("platforms_only") and not on_platform(cfg, c):
            stats["listing_or_irrelevant"] += 1        # not on a platform the user asked for
            continue
        c["emails"] = []
        for e in emails_in(snippet):                       # an address printed in the posting itself
            add_email(c, e, c["url"], from_posting=True)
        st["candidates"].append(c)
        stats["new"] += 1

        score, reason, loc_status, loc = keyword_score(cfg, title, snippet, c["location"], matcher)
        c["keyword_score"], c["keyword_reason"] = score, reason
        if loc_status == "match":
            c["matched_location"] = loc
        if c["key"] and c["key"] in keys:
            miss(st, c, "duplicate"); stats["duplicate"] += 1
            continue
        if cfg["strict_location"] and loc_status == "other":
            miss(st, c, "wrong_location", f"located in {loc}"); stats["wrong_location"] += 1
            continue
        if cfg["ranking"] == "ai":
            if score >= 2:
                c["status"] = "queued"; stats["queued_for_review"] += 1
            else:
                c["fit_score"], c["fit_reason"] = score, f"Keyword score (below AI pre-filter): {reason}"
                miss(st, c, "low_fit"); stats["low_fit"] += 1
            continue
        if cfg["agencies"] == "skip" and AGENCY_HINTS.search(text):
            miss(st, c, "agency"); stats["agency"] += 1
            continue
        if cfg["ranking"] == "keyword":
            qualify_or_reject(st, c, score, f"Keyword score: {reason}")
        else:
            qualify_or_reject(st, c, None, "Not ranked")
        if c["status"] == "rejected":
            stats["low_fit"] += 1
        else:
            stats["qualified"] += 1
            if c["key"]:
                keys.add(c["key"])

    st["dry_searches"] = st.get("dry_searches", 0) + 1     # reset whenever a lead is saved
    if stats["new"] == 0:
        st["consecutive_misses"] += 1
    for b in st.get("boards", []):
        if b["name"] == board:
            b["dry_streak"] = 0 if stats["new"] else b["dry_streak"] + 1
    for c in st["candidates"]:
        if c.get("board") is None:
            c["board"] = board
    return stats


def cmd_apply(args):
    st = load(args)
    cfg = st["config"]
    try:
        updates = json.loads(Path(args.updates).read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Could not read updates JSON: {e}")
    if isinstance(updates, dict):
        updates = updates.get("updates") or [updates]
    matcher = LocationMatcher(cfg["locations"])
    keys = known_keys(st)
    today = today_of(st)
    results, errors = [], []

    for u in updates:
        rc = next((r for r in st.get("rechecks", []) if r["id"] == str(u.get("id", ""))), None)
        if rc:
            rc["result"] = {True: "open", False: "closed"}.get(u.get("open"), "unknown")
            rc["checked"] = today.isoformat()
            results.append({"id": rc["id"], "recheck": rc["result"]})
            continue
        c = cand(st, str(u.get("id", "")))
        if not c:
            errors.append(f"unknown id {u.get('id')}")
            continue
        is_page_check = "open" in u or "page_text" in u
        if ("fit_score" in u or "is_job_posting" in u) and not is_page_check:   # --- verdict
            if c["status"] != "queued":
                errors.append(f"{c['id']}: not waiting for a verdict (status {c['status']})")
                continue
            for f in ("company", "role", "location", "employment_type"):
                v = str(u.get(f) or "").strip()
                if v:
                    c[f] = v
            for f in ("skills_matched", "gaps"):
                v = u.get(f)
                if v:
                    c[f] = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
            c["key"] = dedupe_key(cfg["mode"], c["company"], c["role"]) or c.get("key", "")
            status, loc = matcher.match(c.get("location", ""))
            if status == "match":
                c["matched_location"] = loc
            try:
                score = max(1, min(5, int(round(float(u.get("fit_score", 1))))))
            except (TypeError, ValueError):
                score = 1
            if u.get("is_job_posting") is False:
                miss(st, c, "not_job")
            elif u.get("is_open") is False:
                miss(st, c, "closed", "snippet says closed")
            elif cfg["strict_location"] and status == "other":
                miss(st, c, "wrong_location", f"located in {c.get('location')}")
            elif u.get("is_agency") is True and cfg["agencies"] == "skip":
                miss(st, c, "agency")
            elif c["key"] and c["key"] in keys:
                miss(st, c, "duplicate")
            else:
                qualify_or_reject(st, c, score, str(u.get("fit_reason") or "").strip(), str(u.get("angle") or "").strip())
                if c["status"] != "rejected" and c["key"]:
                    keys.add(c["key"])
        elif is_page_check:                                                # --- page check
            if c["status"] != "needs_open_check":
                errors.append(f"{c['id']}: no page check pending")
                continue
            st["counts"]["page_checked"] = st["counts"].get("page_checked", 0) + 1
            is_open = u.get("open")
            text = str(u.get("page_text") or "")[:4000]
            posted = str(u.get("posted") or "").strip()
            updated = str(u.get("updated") or "").strip()
            est = (estimate_posting(posted, today, assume_posted=True) if posted else None) \
                or estimate_posting(text, today) \
                or (estimate_posting("updated " + updated, today) if updated else None)
            if est or not c.get("date_est"):          # the job page beats the search snippet
                src = "job page" + (f" ({u['posted_source']})" if u.get("posted_source") else "")
                set_date(st, c, est, src)
            if text and (CLOSED_RE.search(text) or closing_passed(text)):
                is_open = False
            rescore = None
            if u.get("fit_score") is not None:                 # the full page can lower (or raise) the fit
                try:
                    rescore = max(1, min(5, int(round(float(u["fit_score"])))))
                except (TypeError, ValueError):
                    rescore = None
            if is_open is False:
                miss(st, c, "closed", "page check")
            elif rescore is not None and rescore < cfg.get("min_score", 3):
                c["fit_score"] = rescore
                if u.get("fit_reason"):
                    c["fit_reason"] = str(u["fit_reason"]).strip()
                miss(st, c, "low_fit", "page check")
            elif c.get("date_verdict") == "out":
                miss(st, c, "outside_window", c.get("posted") or "")
            else:
                for f in ("company", "role", "location"):          # the page often names the employer
                    v = str(u.get(f) or "").strip()
                    cur = str(c.get(f) or "").strip()
                    # fill a blank, or replace a placeholder like "Acme (client not named)" with the real name
                    if v and (not cur or re.search(r"not named|unknown|confidential|hidden|^\?$", cur, re.I)):
                        c[f] = v
                if u.get("company") and not c.get("key"):
                    c["key"] = dedupe_key(cfg["mode"], c["company"], c["role"])
                for f, k in (("fit_reason", "fit_reason"), ("angle", "angle")):   # refreshed after reading the page
                    v = str(u.get(f) or "").strip()
                    if v:
                        c[k] = v
                if rescore is not None:
                    c["fit_score"] = rescore
                c["open_check"] = "Open (page checked)" if is_open else "Unverified (page check failed)"
                route(st, c)
        elif "contact" in u:                                               # --- decision-maker
            if c["status"] != "needs_contact":
                errors.append(f"{c['id']}: no contact lookup pending")
                continue
            ct = u.get("contact") or {}
            link = str(ct.get("url") or "").strip()
            m = re.search(r"linkedin\.com/in/([^/?#]+)", link, re.I)
            if m:
                link = f"https://www.linkedin.com/in/{m.group(1).lower()}"
            c["contact"] = {"name": str(ct.get("name") or "").strip(), "title": str(ct.get("title") or "").strip(),
                            "url": link if link.startswith("http") else ""} if ct else {}
            save_lead(st, c)
        else:
            errors.append(f"{c['id']}: update not understood (expected a verdict, open/page_text, or contact)")
            continue
        results.append({"id": c["id"], "status": c["status"], "outcome": c.get("outcome", "")})

    save(args, st)
    with_next(args, {"ok": not errors, "applied": results, "errors": errors, "saved": st["saved"], "target": cfg["target"]})


def saved_leads(st):
    return sorted((c for c in st["candidates"] if c["status"] == "saved"), key=lambda c: c.get("saved_at", ""))


def lead_status(st, c) -> tuple[str, str]:
    """(Status, Next Step) as shown to the user."""
    a = c.get("application") or {}
    if a.get("status"):
        return JOB_STATUSES.get(a["status"], a["status"]), a.get("next_step", "")
    if st["config"]["mode"] == "jobs":
        via = apply_via(c)
        if "apply yourself" in via:
            return "To apply", f"Apply on {via.split(' (')[0]} yourself (automated applying isn't allowed there)"
        return "To apply", ""
    return "New", ""


def outreach_status(c) -> tuple[str, str]:
    """(Outreach Status, Gmail Status) for a lead: the furthest any of its emails got."""
    os_ = c.get("outreach") or []
    if not os_:
        return "", ""
    order = ["failed", "prepared", "draft", "sent"]
    best = max(os_, key=lambda o: order.index(o["status"]) if o["status"] in order else -1)
    g = {"sent": f"Sent {str(best.get('send_at', ''))[:10]}".strip(), "draft": "Draft in Gmail",
         "failed": f"Failed: {best.get('error', '')}"[:120], "prepared": "Not in Gmail yet"}.get(best["status"], "")
    n = len(os_)
    label = OUTREACH_STATUSES.get(best["status"], best["status"]) + (f" ({n} emails)" if n > 1 else "")
    return label, g


def cmd_plan(args):
    st = load(args)
    cfg = st["config"]
    leads = []
    for c in saved_leads(st):
        status, nxt = lead_status(st, c)
        d = domain_of(c["url"])
        site = c.get("website") or (d if d not in ATS and d not in NO_AUTOMATION and looks_like_company_site(c, d) else "")
        leads.append({"id": c["id"], "company": c.get("company"), "role": c.get("role"), "url": c["url"],
                      "posted": c.get("posted_date") or c.get("posted", ""),
                      "apply_via": apply_via(c), "website": site,
                      "emails": [e["email"] for e in c.get("emails", []) if e.get("email") and is_sendable(e)],
                      "unverified_emails": [e["email"] for e in c.get("emails", []) if e.get("email") and not is_sendable(e)],
                      "fit": c.get("fit_score"), "contacts_checked": bool(c.get("contacts_checked")),
                      "contact_queries": [] if c.get("contacts_checked") else contact_queries(c),
                      "status": status, "next_step": nxt})
    undated = [{"id": c["id"], "company": c.get("company"), "role": c.get("role"), "url": c["url"]}
               for c in st["candidates"] if c["status"] == "undated"]
    out({"mode": cfg["mode"], "window": cfg["posted"], "leads": leads, "undated_separate": undated,
         "policy": cfg.get("policy", {}),
         "todo": {"contacts": [l["id"] for l in leads if not l["contacts_checked"]],
                  "to_apply": [l["id"] for l in leads if cfg["mode"] == "jobs" and l["status"] in ("To apply", "Prepared")],
                  "to_email": [l["id"] for l in leads if l["emails"] and l["status"] in ("New", "To apply", "Prepared")]},
         "next": "Follow SKILL.md step 5 (ask the user what to do next), then references/contacts.md, "
                 "references/applying.md or references/outreach.md."})


HIRING_LOCAL = re.compile(r"^(careers?|jobs?|hr|hiring|recruit\w*|talent|people|apply|cv|resumes?|join)\b", re.I)


def has_hiring_contact(c) -> bool:
    """A verified recruiter/HR person, or a verified hiring inbox (careers@, jobs@, hr@...)."""
    for e in c.get("emails", []):
        if not e.get("email") or not is_sendable(e):
            continue
        if e["type"].startswith("Named") and re.search(r"recruit|talent|hr\b|human|people|hiring|founder|ceo|cto", e.get("role") or "", re.I):
            return True
        if e["type"] == "Generic" and HIRING_LOCAL.match(e["email"].split("@")[0]):
            return True
    return False


def contact_queries(c) -> list:
    """Searches for the company's own HR/recruiter emails when the job post and board give none."""
    co = (c.get("company") or "").strip()
    co = re.sub(r"\s*\((client )?not named\)|\s*\(talent platform\)", "", co, flags=re.I).strip()
    if not co:
        return []
    city = re.split(r"[,(]", c.get("location") or "")[0].strip()
    city = "" if re.search(r"remote|anywhere|worldwide", city, re.I) else city
    q = [f'"{co}" official website', f'"{co}" careers email', f'"{co}" HR email {city}'.strip(),
         f'"{co}" recruiter OR "talent acquisition" OR "HR manager" {city}'.strip()]
    site = c.get("website")
    if site and site not in ATS:
        q = [f"{site} careers", f"{site} contact", f'"@{site}" careers OR hr OR jobs OR recruiting'] + q[1:]
    return q


def cmd_contacts(args):
    """Record emails found on public pages. Each email needs the page it was on (source_url) and the
    exact text around it (evidence), which must contain the address. Guessed addresses are refused."""
    st = load(args)
    try:
        updates = json.loads(Path(args.updates).read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Could not read contacts JSON: {e}")
    if isinstance(updates, dict):
        updates = [updates]
    added, refused, incomplete = [], [], []
    for u in updates:
        c = cand(st, str(u.get("id", "")))
        if not c or c["status"] != "saved":
            refused.append({"id": u.get("id"), "why": "unknown or unsaved lead"})
            continue
        if u.get("website"):
            wd = domain_of(str(u["website"])) or str(u["website"])
            if wd == domain_of(c["url"]) and not looks_like_company_site(c, wd):
                refused.append({"id": c["id"], "website": wd,
                                "why": "that is the job board's site, not the company's; search for the company's own website"})
            else:
                c["website"] = wd
            for e in c.get("emails", []):                  # re-judge earlier addresses now the site is known
                if not e["verification"].startswith("Verified: in the job post"):
                    e["verification"] = email_verification(c, e["email"], e["source"], False)
        for ppl in u.get("people") or []:                  # named recruiters/HR/founders with no public email
            nm, src, ev = str(ppl.get("name") or "").strip(), str(ppl.get("source_url") or "").strip(), str(ppl.get("evidence") or "")
            if not nm or not src.startswith("http") or nm.split()[0].lower() not in ev.lower():
                refused.append({"id": c["id"], "person": nm, "why": "people need name, source_url and evidence quoting the name"})
                continue
            if any(x.get("name", "").lower() == nm.lower() and not x.get("email") for x in c.setdefault("emails", [])):
                continue
            c["emails"].append({"email": "", "name": nm, "role": str(ppl.get("role") or "").strip(), "type": "Named",
                                "source": src, "verification": "No public email (named contact only)"})
            added.append({"id": c["id"], "person": nm})
        for e in u.get("emails") or []:
            email = str(e.get("email") or "").strip().lower()
            src = str(e.get("source_url") or "").strip()
            evidence = str(e.get("evidence") or "")
            if not src.startswith("http"):
                refused.append({"id": c["id"], "email": email, "why": "missing source_url (the page it was found on)"})
                continue
            if email not in evidence.lower():
                refused.append({"id": c["id"], "email": email, "why": "evidence must quote the page text that shows this address (no guessing)"})
                continue
            why = add_email(c, email, src, e.get("name"), e.get("role"), from_posting=(normalize_job_url(src) == c.get("nurl")))
            (refused.append({"id": c["id"], "email": email, "why": why}) if why else added.append({"id": c["id"], "email": email}))
        if u.get("website") or u.get("website_searched") or u.get("no_website"):
            c["website_searched"] = True
        # Done only when a hiring contact is found, or the company's own website was searched too.
        if has_hiring_contact(c) or c.get("website_searched"):
            c["contacts_checked"] = True
        else:
            incomplete.append({"id": c["id"], "company": c.get("company"),
                               "why": "no verified HR/recruiter/careers email yet: search the company by name, open its own "
                                      "website (careers, contact, about, team pages) and send this lead again with "
                                      "website + any emails (or no_website: true if it has none)",
                               "queries": contact_queries(c)})
    save(args, st)
    out({"ok": True, "added": added, "refused": refused, "incomplete": incomplete,
         "next": "Do the company-website step for every lead in `incomplete`, then run `contacts` again." if incomplete
                 else "Run `jword.py plan` to see what's left."})


def cmd_track(args):
    """Record what happened with an application or email: status + next step for the user."""
    st = load(args)
    try:
        updates = json.loads(Path(args.updates).read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Could not read track JSON: {e}")
    if isinstance(updates, dict):
        updates = [updates]
    done_, errors = [], []
    for u in updates:
        c = cand(st, str(u.get("id", "")))
        status = str(u.get("status") or "").strip().lower().replace(" ", "_")
        if not c or c["status"] != "saved":
            errors.append(f"{u.get('id')}: unknown or unsaved lead")
            continue
        if status not in JOB_STATUSES:
            errors.append(f"{c['id']}: status must be one of {sorted(JOB_STATUSES)}")
            continue
        if status == "applied" and "apply yourself" in apply_via(c) and not u.get("by_user"):
            errors.append(f"{c['id']}: {apply_via(c)} - Claude must not submit there; set by_user: true if the user applied")
            continue
        a = c.setdefault("application", {})
        a.update({"status": status, "next_step": str(u.get("next_step") or "").strip(),
                  "updated_at": dt.datetime.now().isoformat(timespec="seconds")})
        for k in ("message", "answers", "method"):
            if u.get(k):
                a[k] = str(u[k])[:4000]
        if status in ("applied", "emailed") and not a.get("done_at"):
            a["done_at"] = a["updated_at"]
        done_.append({"id": c["id"], "status": JOB_STATUSES[status]})
    save(args, st)
    out({"ok": not errors, "updated": done_, "errors": errors})



# ============================================================================ outreach + Gmail


def norm_body(txt: str, *drop) -> str:
    t = str(txt or "").lower()
    for d in drop:
        if d:
            t = t.replace(str(d).lower(), " ")
    t = re.sub(r"^\s*(hi|hello|dear|hey)[^\n]*\n", "", t)          # greeting line
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def all_outreach(st):
    for c in st["candidates"]:
        for o in c.get("outreach", []):
            yield c, o


def cmd_settings(args):
    """Store the user's choices (asked in SKILL.md step 3). External actions are checked against them."""
    st = load(args)
    pol = st["config"].setdefault("policy", {})
    if args.email_mode:
        pol["email_mode"] = args.email_mode
    if args.submit_mode:
        pol["submit_mode"] = args.submit_mode
    if args.contact_research:
        pol["contact_research"] = args.contact_research
    save(args, st)
    out({"ok": True, "policy": pol, "email_mode": EMAIL_MODES.get(pol.get("email_mode"), "not set"),
         "note": "B2B (clients mode) emails are never sent automatically: 'auto' acts as 'approve_each' there."})


def cmd_outreach(args):
    """Record individual emails written for verified contacts. Refuses guessed or unverified recipients,
    unfilled placeholders, copy-paste emails across companies and repeat outreach."""
    st = load(args)
    cfg = st["config"]
    pol = cfg.get("policy", {})
    if pol.get("email_mode") == "contacts_only":
        fail("Email mode is 'contacts_only': the user asked for contacts only, so no emails are prepared.")
    try:
        updates = json.loads(Path(args.updates).read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Could not read outreach JSON: {e}")
    if isinstance(updates, dict):
        updates = [updates]
    purpose = "application" if cfg["mode"] == "jobs" else "b2b"
    prior = {k.lower(): v for k, v in st.get("prior_outreach", {}).items()}
    accepted, refused = [], []
    for u in updates:
        c = cand(st, str(u.get("id", "")))
        to = str(u.get("to") or "").strip().lower()
        subj, body = str(u.get("subject") or "").strip(), str(u.get("body") or "").strip()
        why = ""
        e = next((x for x in (c or {}).get("emails", []) if x.get("email") == to), None)
        if not c or c["status"] != "saved":
            why = "unknown or unsaved lead"
        elif not e:
            why = "recipient is not a recorded contact for this lead (record it with `contacts` first; never guess)"
        elif not is_sendable(e):
            why = f"recipient not verified ({e['verification']})"
        elif not subj or len(body.split()) < 40:
            why = "needs a subject and a real body (40+ words)"
        elif len(body.split()) > 260:
            why = "too long: keep it under ~220 words"
        elif PLACEHOLDER_RE.search(subj + "\n" + body):
            why = "unfilled placeholder in the text: " + PLACEHOLDER_RE.search(subj + "\n" + body).group(0)
        elif purpose == "b2b" and not OPT_OUT_RE.search(body):
            why = "B2B outreach needs a short opt-out line (e.g. 'If this isn't relevant, just say so and I won't follow up.')"
        elif (to in prior or any(o["to"] == to and o["status"] in ("prepared", "draft", "sent") for _, o in all_outreach(st))) \
                and not u.get("override_duplicate"):
            why = (f"already contacted ({prior.get(to, 'this run')}); don't email again unless the user explicitly says so "
                   "(then add override_duplicate: true)")
        else:
            nb = norm_body(body, c.get("company"), e.get("name"))
            for c2, o2 in all_outreach(st):
                if c2["id"] == c["id"] and o2["to"] == to:
                    continue
                if o2["subject"].strip().lower() == subj.lower() and (c2.get("company") or "") != (c.get("company") or ""):
                    why = f"same subject as the email to {c2.get('company')}: write a subject for this job"
                    break
                ratio = difflib.SequenceMatcher(None, nb, norm_body(o2["body"], c2.get("company"), o2.get("name"))).ratio()
                if ratio > 0.82:
                    why = f"{int(ratio * 100)}% identical to the email for {c2.get('company')}: personalise it for this company and job"
                    break
        if why:
            refused.append({"id": u.get("id"), "to": to, "why": why})
            continue
        oid = f"o{sum(1 for _ in all_outreach(st)) + 1}"
        c.setdefault("outreach", []).append({
            "oid": oid, "to": to, "name": e.get("name", ""), "recipient_type": e["type"], "subject": subj, "body": body,
            "purpose": purpose, "status": "prepared", "gmail_id": "", "error": "",
            "attach_cv": bool(u.get("attach_cv")), "prepared_at": dt.datetime.now().isoformat(timespec="seconds")})
        accepted.append({"oid": oid, "id": c["id"], "company": c.get("company"), "to": to, "subject": subj})
    save(args, st)
    out({"ok": not refused, "accepted": accepted, "refused": refused,
         "next": "Show the user recipients + subjects, then run `jword.py outbox` to see what the chosen mode allows."})


def allowed_action(st, o) -> str:
    mode = st["config"].get("policy", {}).get("email_mode", "drafts")
    if mode in ("contacts_only", "chat"):
        return "none"
    if mode == "drafts":
        return "draft"
    if mode == "approve_each" or o["purpose"] == "b2b":
        return "send_after_approval"
    sent = sum(1 for _, x in all_outreach(st) if x["status"] == "sent")
    return "send" if sent < AUTO_SEND_CAP else "send_after_approval"


def cmd_outbox(args):
    st = load(args)
    items = []
    for c, o in all_outreach(st):
        if o["status"] in ("prepared", "failed", "draft"):
            act = allowed_action(st, o)
            if o["status"] == "draft" and act == "draft":
                continue
            items.append({"oid": o["oid"], "company": c.get("company"), "to": o["to"], "subject": o["subject"],
                          "status": OUTREACH_STATUSES[o["status"]], "gmail_id": o.get("gmail_id", ""),
                          "allowed": act, "attach_cv": o.get("attach_cv", False)})
    mode = st["config"].get("policy", {}).get("email_mode", "drafts")
    out({"email_mode": EMAIL_MODES.get(mode, mode), "items": items,
         "how": "allowed=draft -> Gmail create_draft; send -> Gmail send_message (or send the draft by draftId); "
                "send_after_approval -> show the email, wait for the user's yes, then send; none -> show in chat only. "
                "After EVERY connector call run `jword.py gmail --updates <file>` with "
                "{oid, action: draft|send, ok, id: '<id the connector returned>', error, approved_by_user}."})


def cmd_gmail(args):
    """Record Gmail connector results. A draft/send counts only with the id the connector returned."""
    st = load(args)
    try:
        updates = json.loads(Path(args.updates).read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Could not read gmail JSON: {e}")
    if isinstance(updates, dict):
        updates = [updates]
    done_, refused = [], []
    for u in updates:
        hit = next(((c, o) for c, o in all_outreach(st) if o["oid"] == str(u.get("oid", ""))), None)
        if not hit:
            refused.append({"oid": u.get("oid"), "why": "unknown outreach id"})
            continue
        c, o = hit
        action = str(u.get("action") or "").lower()
        allowed = allowed_action(st, o)
        if action not in ("draft", "send"):
            refused.append({"oid": o["oid"], "why": "action must be draft or send"})
            continue
        if o["status"] == "sent":
            refused.append({"oid": o["oid"], "why": "already sent: never send twice"})
            continue
        if action == "send" and allowed in ("none", "draft"):
            refused.append({"oid": o["oid"], "why": f"policy violation: sending is not allowed in '{st['config'].get('policy', {}).get('email_mode')}' mode"})
            o["error"] = "send attempted outside the chosen mode"
            continue
        if action == "send" and allowed == "send_after_approval" and not u.get("approved_by_user"):
            refused.append({"oid": o["oid"], "why": "this email needs the user's explicit approval before sending (approved_by_user: true)"})
            continue
        if action == "draft" and allowed == "none":
            refused.append({"oid": o["oid"], "why": "mode is chat/contacts only: no Gmail drafts"})
            continue
        gid = str(u.get("id") or "").strip()
        now_ = dt.datetime.now().isoformat(timespec="seconds")
        if u.get("ok") and gid:
            o["status"] = "sent" if action == "send" else "draft"
            o["gmail_id"], o["error"], o[f"{action}_at"] = gid, "", now_
        else:
            o["status"] = "failed"
            o["error"] = str(u.get("error") or "connector returned no id, so it is not counted as done")[:300]
        st.setdefault("gmail_log", []).append({"oid": o["oid"], "action": action, "ok": o["status"] != "failed",
                                               "id": gid, "error": o["error"], "at": now_})
        done_.append({"oid": o["oid"], "company": c.get("company"), "status": OUTREACH_STATUSES[o["status"]]})
    save(args, st)
    out({"ok": not refused, "recorded": done_, "refused": refused})


def cmd_log(args):
    st = load(args)
    if args.agents:
        st.setdefault("agents_used", []).append(args.agents)
    if args.note:
        st["notes"].append(args.note)
    if args.error:
        st.setdefault("errors", []).append(args.error)
    save(args, st)
    out({"ok": True})


def cmd_shards(args):
    """Claude Code: split the next searches into independent work packets for parallel job-researcher
    subagents. Every packet carries the same strict window and rules; results come back as
    {query_id: [results]} files for `ingest`."""
    st = load(args)
    cfg = st["config"]
    workers, per = max(1, min(int(args.workers), 5)), max(1, min(int(args.per_worker), 6))
    left = max(0, cfg["max_searches"] - st["searches"] - len(st.get("issued", {})))
    combos = [(r, l) for r in cfg["roles"] for l in cfg["locations"]]
    groups = {f"w{k + 1}": [] for k in range(workers)}
    for n in range(min(left, workers * per)):
        plan = build_query(st)
        st["query_index"] += 1
        qid = f"q{st['query_index']}"
        st.setdefault("issued", {})[qid] = plan
        groups[f"w{n % workers + 1}"].append({"query_id": qid, "query": plan["query"], "board": plan["board_label"]})
    groups = {k: v for k, v in groups.items() if v}
    packets = []
    for n, (g, qs) in enumerate(groups.items(), 1):
        packets.append({"shard": f"s{n}", "focus": g, "queries": qs, "window": cfg.get("window"),
                        "window_label": cfg["posted"], "rules": "Run each query exactly. Return ALL results per query_id "
                        "as {query_id: [{title,url,snippet}]}; keep any posted/updated dates in the snippet; never "
                        "invent results; do not filter by date yourself (the engine applies the window)."})
    save(args, st)
    out({"packets": packets, "next": "Give each packet to one job-researcher. When all return, run "
                                     "`jword.py ingest --results <file>` per packet, then `jword.py next`."})


def cmd_profile_check(args):
    p = Path(args.profile)
    if not p.exists():
        fail(f"Profile not found: {p}. Create it from references/applicant-profile.md.")
    try:
        prof = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Profile is not valid JSON: {e}")
    cv = str(prof.get("cv_path") or "").strip()
    has_cv = bool(cv) and Path(cv).exists()
    writing = [k for k in ("full_name",) if prof.get(k) in (None, "", [], {})]
    if not (has_cv or (prof.get("experience") and prof.get("skills"))):
        writing.append("cv_path (a CV file) or experience + skills")
    forms = [k for k in PROFILE_REQUIRED if prof.get(k) in (None, "", [], {}) and k not in writing]
    out({"ok": not writing and not forms, "ready_for_writing": not writing, "ready_for_forms": not writing and not forms,
         "missing_for_writing": writing, "missing_for_forms": forms, "missing": writing + forms,
         "cv_file": cv if has_cv else "",
         "cv_upload_note": "" if has_cv else "No CV file: forms that require an upload will be marked 'Needs you: upload CV'.",
         "eeo": prof.get("eeo_answers", "ask"),
         "next": ("Ask the user for: " + ", ".join(writing) + " (needed before writing anything).") if writing else
                 ("Write the cover letters and emails now. Ask for " + ", ".join(forms) + " only before filling forms.")
                 if forms else "Profile is ready for writing and forms."})


def cmd_report(args):
    """Markdown status list for the end of the chat."""
    st = load(args)
    cfg = st["config"]
    rows, counts = [], {}
    for i, c in enumerate(saved_leads(st), 1):
        status, nxt = lead_status(st, c)
        ostat, _ = outreach_status(c)
        email = best_email(c) or "-"
        posted = c.get("posted_date") or c.get("posted") or "-"
        rows.append(f"| {i} | {c.get('company') or '?'} | [{c.get('role') or 'Job'}]({c['url']}) | {posted} | {c.get('fit_score') or '-'} "
                    f"| {apply_via(c)} | {email} | **{status}** | {ostat or '-'} | {nxt or '-'} |")
        counts[status] = counts.get(status, 0) + 1
    head = ("| # | Company | Job | Posted | Fit | Apply via | Email | Application | Outreach | Next step |\n"
            "|---|---|---|---|---|---|---|---|---|---|")
    md = f"**Posting window:** {cfg['posted']}\n\n" + head + "\n" + "\n".join(rows)
    und = [c for c in st["candidates"] if c["status"] == "undated"]
    if und:
        md += "\n\n**Undated jobs (no verifiable posting date; listed separately as you asked):**\n" + "\n".join(
            f"- {c.get('company') or '?'}: [{c.get('role') or 'Job'}]({c['url']})" for c in und)
    cnt = st["counts"]
    excl = {REJECT_REASONS.get(k, k): v for k, v in cnt.items() if k in REJECT_REASONS and v}
    out({"markdown": md, "totals": counts, "excluded": excl,
         "gmail": {k: sum(1 for _, o in all_outreach(st) if o["status"] == k) for k in OUTREACH_STATUSES}})


def summary(st) -> dict:
    cfg, cnt = st["config"], st["counts"]
    return {
        "run_id": st["run_id"], "status": st["status"], "saved": st["saved"], "target": cfg["target"],
        "saved_by_source": st["saved_by_source"], "searches": st["searches"], "max_searches": cfg["max_searches"],
        "window": cfg["posted"],
        "skipped": {k: cnt.get(k, 0) for k in ("low_fit", "duplicate", "closed", "wrong_location", "agency", "not_job",
                                                "outside_window", "no_date", "paywalled")},
        "page_checked": cnt.get("page_checked", 0),
        "waiting": {s: sum(1 for c in st["candidates"] if c["status"] == s) for s in ("queued", "ready") + IN_FLIGHT},
    }


def cmd_status(args):
    out(summary(load(args)))


def cmd_export(args):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    st = load(args)
    cfg = st["config"]
    if st["status"] == "running":
        st["status"] = "stopped_early"
    now = dt.datetime.now()
    mode_label = "Jobs" if cfg["mode"] == "jobs" else "Clients"

    def lead_row(c, verification_extra=""):
        ct = c.get("contact") or {}
        named = next((e for e in c.get("emails", []) if e["type"].startswith("Named") and e.get("name")), None)
        contact = ct.get("name", "") or (named or {}).get("name", "")
        title = ct.get("title", "") or (named or {}).get("role", "")
        if contact and title:
            contact = f"{contact} ({title})"
        email = best_email(c)
        esrc = next((e["source"] for e in c.get("emails", []) if e.get("email") == email), "")
        ostat, gstat = outreach_status(c)
        app_status, nxt = lead_status(st, c)
        ver = [c.get("open_check") or ""]
        if cfg.get("window"):
            ver.append({"in": "date in window", "out": "date outside window"}.get(c.get("date_verdict"), "no verifiable date"))
        if verification_extra:
            ver.append(verification_extra)
        gaps = f" Gaps: {c['gaps']}." if c.get("gaps") else ""
        posted = c.get("posted_date") or ""
        if c.get("posted") and c["posted"] != posted:
            posted = f"{posted} ({c['posted']})" if posted else c["posted"]
        return {
            "Date Added": (c.get("saved_at") or now.isoformat())[:10], "Mode": mode_label,
            "Company": c.get("company", ""), "Job Title": c.get("role", ""), "Location": c.get("location", ""),
            "Employment Type": c.get("employment_type", ""), "Posted": posted, "Posting Window": cfg["posted"],
            "Date Source": c.get("date_source", ""), "Source": c["source"], "Job URL": c["url"],
            "Verification": "; ".join(v for v in ver if v),
            "Fit Score": c.get("fit_score") if c.get("fit_score") is not None else "",
            "Why It Fits": (c.get("fit_reason", "") + gaps).strip(), "Relevant Skills": c.get("skills_matched", ""),
            "Pitch / Tip": c.get("angle", ""), "Contact": contact, "Email": email,
            "Contact Source": ct.get("url", "") or esrc, "Apply Via": apply_via(c) if cfg["mode"] == "jobs" else "",
            "Application Status": app_status, "Outreach Status": ostat, "Gmail Status": gstat,
            "Next Step": nxt, "Run ID": st["run_id"],
        }

    new_rows = [lead_row(c) for c in saved_leads(st)]
    undated_rows = [lead_row(c, "NO VERIFIABLE POSTING DATE (listed separately)")
                    for c in st["candidates"] if c["status"] == "undated"]
    new_contacts, new_apps = [], []
    by_email = {}
    for c in saved_leads(st):
        for e in c.get("emails", []):
            sent = [o for o in c.get("outreach", []) if o["to"] == e.get("email") and e.get("email")]
            ostat = OUTREACH_STATUSES.get(sent[-1]["status"], "") if sent else ""
            key = e.get("email") or f"{c.get('company')}|{e.get('name')}"
            job = f"{c.get('role', '')} ({c['url']})"
            if key in by_email:                           # same address for several jobs: one row, all jobs
                r = by_email[key]
                if job not in r["Associated Job"]:
                    r["Associated Job"] += "; " + job
                r["Outreach Status"] = r["Outreach Status"] or ostat
                continue
            r = {"Company": c.get("company", ""), "Name": e.get("name", ""), "Role": e.get("role", ""),
                 "Email": e.get("email", "") or "(no public email)", "Type": e["type"], "Source URL": e["source"],
                 "Verification": e.get("verification", ""), "Associated Job": job, "Outreach Status": ostat,
                 "Run ID": st["run_id"]}
            by_email[key] = r
            new_contacts.append(r)
        a = c.get("application") or {}
        outs = c.get("outreach") or [None]
        if not a.get("status") and outs == [None]:
            continue
        for k, o in enumerate(outs):
            o = o or {}
            g = {"sent": f"Sent {str(o.get('send_at', ''))[:10]} (id {o.get('gmail_id', '')})",
                 "draft": f"Draft created (id {o.get('gmail_id', '')})", "failed": f"Failed: {o.get('error', '')}",
                 "prepared": "Prepared (not in Gmail)", "skipped": "Skipped"}.get(o.get("status"), "")
            new_apps.append({
                "Date": (a.get("done_at") or a.get("updated_at") or o.get("prepared_at") or now.isoformat())[:10],
                "Company": c.get("company", ""), "Job Title": c.get("role", ""), "Job URL": c["url"],
                "Apply Via": a.get("method") or apply_via(c),
                "Application Status": JOB_STATUSES.get(a.get("status"), a.get("status", "")) if a else "",
                "Cover Letter": a.get("message", "") if k == 0 else "(see row above)",
                "Application Answers": a.get("answers", "") if k == 0 else "",
                "Outreach To": o.get("to", ""), "Outreach Subject": o.get("subject", ""), "Outreach Body": o.get("body", ""),
                "Gmail Status": g, "Next Action": a.get("next_step", "") or ("Review the Gmail draft and send it" if o.get("status") == "draft" else ""),
                "Run ID": st["run_id"]})

    cnt = st["counts"]
    gl = st.get("gmail_log", [])
    emails_all = [e for c in saved_leads(st) for e in c.get("emails", []) if e.get("email")]
    run_row = {
        "Run ID": st["run_id"], "Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"),
        "Run By": cfg["run_by"], "Mode": mode_label, "Roles": ", ".join(cfg["roles"]),
        "Locations": ", ".join(cfg["locations"]) + ("" if cfg["strict_location"] else " (not filtered)"),
        "Posting Window": cfg["posted"], "Undated Jobs": ("listed separately" if cfg.get("undated") == "separate" else "excluded")
        + f" ({len(undated_rows) if cfg.get('undated') == 'separate' else cnt.get('no_date', 0)})",
        "Platforms": ", ".join(cfg.get("platforms") or ["Any"]) + (" (only)" if cfg.get("platforms_only") else ""),
        "Agents Used": "; ".join(st.get("agents_used", [])) or "Single assistant (sequential)",
        "Ranking": {"ai": "AI (Claude)", "keyword": "Keyword", "none": "None"}[cfg["ranking"]],
        "Min Score": "" if cfg["ranking"] == "none" else cfg["min_score"], "Target": cfg["target"],
        "Saved": st["saved"],
        "Saved By Source": ", ".join(f"{k}: {v}" for k, v in sorted(st["saved_by_source"].items(), key=lambda x: -x[1])),
        "Searches": st["searches"], "Candidates Reviewed": len(st["candidates"]), "Page Checked": cnt.get("page_checked", 0),
        "Rejected (reasons)": "; ".join(f"{REJECT_REASONS[k]}: {v}" for k, v in cnt.items() if k in REJECT_REASONS and v),
        "Duplicates": cnt.get("duplicate", 0), "Outside Window": cnt.get("outside_window", 0), "No Date": cnt.get("no_date", 0),
        "Contacts Verified": sum(1 for e in emails_all if is_sendable(e)),
        "Contacts Unverified": sum(1 for e in emails_all if not is_sendable(e)),
        "Gmail Drafts": sum(1 for g in gl if g["action"] == "draft" and g["ok"]),
        "Gmail Sent": sum(1 for g in gl if g["action"] == "send" and g["ok"]),
        "Gmail Failed": sum(1 for g in gl if not g["ok"]),
        "Applied": sum(1 for c in saved_leads(st) if (c.get("application") or {}).get("status") == "applied"),
        "Needs You": sum(1 for c in saved_leads(st) if (c.get("application") or {}).get("status") == "needs_you"),
        "Status": st["status"], "Errors / Limitations": "; ".join(st["notes"] + st.get("errors", [])),
    }

    old_leads = []
    for i_, r in enumerate(st["existing"]["leads"]):
        r = dict(r)
        rc = next((x for x in st.get("rechecks", []) if x["row"] == i_ and x["result"]), None)
        if rc and rc["result"] == "closed":
            r["Verification"] = f"Closed since last run (checked {rc['checked']})"
            if str(r.get("Application Status") or "") in ("To apply", "Prepared", "New", ""):
                r["Next Step"] = "Job closed: no action needed"
        elif rc and rc["result"] == "open":
            r["Verification"] = f"Still open (re-checked {rc['checked']})"
        old_leads.append(r)
    leads = old_leads + new_rows
    runlog = list(st["existing"]["runlog"]) + [run_row]
    contacts = list(st["existing"].get("contacts", [])) + new_contacts
    apps = list(st["existing"].get("applications", [])) + new_apps
    excluded = list(st["existing"].get("excluded", []))
    excluded += [{"Run ID": st["run_id"], "Title / Company": f"{c.get('company') or ''} {c.get('role') or c['title']}".strip(),
                  "URL": c["url"], "Reason": REJECT_REASONS.get(c.get("outcome"), c.get("outcome", "")),
                  "Detail": c.get("note") or (c.get("fit_reason", "") if c.get("outcome") == "low_fit" else "")}
                 for c in st["candidates"] if c["status"] == "rejected"]
    excluded += [{"Run ID": st["run_id"], "Title / Company": x["title"], "URL": x["url"],
                  "Reason": REJECT_REASONS.get(x["outcome"], x["outcome"]), "Detail": x.get("note", "")}
                 for x in st.get("excluded", [])]

    wb = openpyxl.Workbook()
    head_fill = PatternFill("solid", start_color="1F3864")
    head_font = Font(name="Arial", bold=True, color="FFFFFF")
    body_font = Font(name="Arial", size=10)
    link_font = Font(name="Arial", size=10, color="0563C1", underline="single")
    score_fill = {5: "C6EFCE", 4: "E2EFDA", 3: "FFF2CC", 2: "FCE4D6", 1: "F8CBAD"}
    widths = {"Posted": 22, "Posting Window": 30, "Date Source": 24, "Verification": 34, "Relevant Skills": 32,
              "Source URL": 40, "Associated Job": 44, "Outreach Subject": 36, "Outreach Body": 60, "Gmail Status": 28,
              "Cover Letter": 60, "Application Answers": 40, "Next Action": 34, "Rejected (reasons)": 44,
              "Errors / Limitations": 40, "Title / Company": 40, "URL": 44, "Reason": 30, "Detail": 30, "Company": 24, "Job Title": 30, "Location": 22, "Source": 16, "Job URL": 40, "Why It Fits": 48,
              "Pitch / Tip": 48, "Contact": 28, "Contact Link": 34, "Roles": 30, "Locations": 26,
              "Saved By Source": 36, "Notes": 40, "Email": 30, "Apply Via": 22, "Next Step": 36, "Found On": 40,
              "Cover Letter / Message": 60, "Answers Used": 40, "Name": 22, "Role": 24}

    def write(ws, cols, rows):
        ws.append(cols)
        for i, col in enumerate(cols, 1):
            cell = ws.cell(row=1, column=i)
            cell.font, cell.fill = head_font, head_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = widths.get(col, max(12, len(col) + 2))
        for r in rows:
            ws.append([r.get(c, "") for c in cols])
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                col = cols[cell.column - 1]
                cell.font = body_font
                cell.alignment = Alignment(vertical="top", wrap_text=col in ("Why It Fits", "Pitch / Tip", "Errors / Limitations", "Next Step",
                                                                             "Cover Letter", "Application Answers", "Outreach Body",
                                                                             "Associated Job", "Rejected (reasons)"))
                if col in ("Job URL", "Contact Source", "Source URL", "URL") and str(cell.value or "").startswith("http"):
                    cell.hyperlink, cell.font = str(cell.value), link_font
                if col == "Fit Score" and str(cell.value).isdigit():
                    cell.fill = PatternFill("solid", start_color=score_fill.get(int(cell.value), "FFFFFF"))
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
        ws.row_dimensions[1].height = 22

    ws = wb.active
    ws.title = "Leads"
    write(ws, LEAD_COLUMNS, leads)
    write(wb.create_sheet("Contacts"), CONTACT_COLUMNS, contacts)
    write(wb.create_sheet("Applications"), APPLICATION_COLUMNS, apps)
    write(wb.create_sheet("Run Log"), RUNLOG_COLUMNS, runlog)
    if undated_rows:
        write(wb.create_sheet("Undated Jobs"), LEAD_COLUMNS, undated_rows)
    write(wb.create_sheet("Excluded"), EXCLUDED_COLUMNS, excluded)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    wb.save(outp)
    save(args, st)
    out({"ok": True, "file": str(outp), "new_leads": len(new_rows), "total_leads": len(leads), "undated": len(undated_rows),
         "emails_found": len(new_contacts), "applications_tracked": len(new_apps), "summary": summary(st),
         "next": "Run `jword.py report` and show its markdown table to the user with the file."})


# ============================================================================ cli


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jword.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="jword_run/state.json", help="run state file (default: jword_run/state.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="start a new run")
    p.add_argument("--mode", choices=["clients", "jobs"], required=True)
    p.add_argument("--roles", required=True, help='comma-separated, e.g. "Flutter Developer, AI Engineer"')
    p.add_argument("--locations", required=True, help='comma-separated cities/countries, "Remote" or "Anywhere"')
    p.add_argument("--offer", default="", help="what the user sells (clients) or a CV summary (jobs)")
    p.add_argument("--ranking", choices=["ai", "keyword", "none"], default="ai")
    p.add_argument("--min-score", default=3)
    p.add_argument("--posted-within", default="", help="STRICT posting window: 24h, 3d, 7d, 14d, 30d, 60d, 'last 10 days', "
                   "'this week', '2026-11-01..2026-11-10', 'between Nov 1 and Nov 10', or 'any' (default 7d)")
    p.add_argument("--posted", default="", help="legacy alias of --posted-within (day/week/month/any)")
    p.add_argument("--undated", choices=["exclude", "separate"], default="exclude",
                   help="jobs with no verifiable posting date: drop them (default) or list them separately")
    p.add_argument("--verify-open", choices=["yes", "no"], default="yes")
    p.add_argument("--find-contacts", choices=["yes", "no"], default="yes")
    p.add_argument("--location-filter", choices=["strict", "keep-all"], default="strict")
    p.add_argument("--agencies", choices=["skip", "keep"], default="", help="recruitment-agency posts (default: skip in clients mode)")
    p.add_argument("--platforms", default="", help=f"preferred platforms, comma-separated: {', '.join(PLATFORMS)}")
    p.add_argument("--platforms-only", action="store_true", help="keep only results from --platforms")
    p.add_argument("--target", default=10)
    p.add_argument("--run-by", default="")
    p.add_argument("--existing", default="", help="earlier Jword .xlsx/.csv: skip its leads and append to it on export")
    p.add_argument("--recheck-previous", action="store_true", help="re-check earlier jobs and mark the ones that closed")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("next", help="what to do next")
    p.add_argument("--batch", default=REVIEW_BATCH, help="candidates per review step (Claude Code: up to 12)")
    p.add_argument("--max-tasks", default=5, help="page checks per verify step (Claude Code: up to 15)")
    p.set_defaults(fn=cmd_next)
    p = sub.add_parser("ingest", help="feed web-search results")
    p.add_argument("--results", required=True)
    p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("apply", help="feed verdicts / page checks / contacts")
    p.add_argument("--updates", required=True)
    p.set_defaults(fn=cmd_apply)
    sub.add_parser("status", help="progress summary").set_defaults(fn=cmd_status)
    sub.add_parser("plan", help="saved leads and what's left to do").set_defaults(fn=cmd_plan)
    p = sub.add_parser("contacts", help="record emails found on public pages")
    p.add_argument("--updates", required=True)
    p.set_defaults(fn=cmd_contacts)
    p = sub.add_parser("track", help="record application / email outcomes")
    p.add_argument("--updates", required=True)
    p.set_defaults(fn=cmd_track)
    p = sub.add_parser("profile-check", help="check the applicant profile")
    p.add_argument("--profile", required=True)
    p.set_defaults(fn=cmd_profile_check)
    p = sub.add_parser("settings", help="store the user's contact / email / submit choices")
    p.add_argument("--email-mode", choices=list(EMAIL_MODES), default="")
    p.add_argument("--submit-mode", choices=list(SUBMIT_MODES), default="")
    p.add_argument("--contact-research", choices=["jobs_only", "contacts", "contacts_outreach"], default="")
    p.set_defaults(fn=cmd_settings)
    p = sub.add_parser("outreach", help="record individual emails for verified contacts")
    p.add_argument("--updates", required=True)
    p.set_defaults(fn=cmd_outreach)
    sub.add_parser("outbox", help="what the chosen email mode allows for each prepared email").set_defaults(fn=cmd_outbox)
    p = sub.add_parser("gmail", help="record Gmail connector results (draft/send ids)")
    p.add_argument("--updates", required=True)
    p.set_defaults(fn=cmd_gmail)
    p = sub.add_parser("shards", help="Claude Code: split searches into parallel work packets")
    p.add_argument("--workers", default=3)
    p.add_argument("--per-worker", default=3)
    p.set_defaults(fn=cmd_shards)
    p = sub.add_parser("log", help="note agents used, limitations or errors for the Run Log")
    p.add_argument("--agents", default="")
    p.add_argument("--note", default="")
    p.add_argument("--error", default="")
    p.set_defaults(fn=cmd_log)
    sub.add_parser("report", help="final status list (markdown)").set_defaults(fn=cmd_report)
    p = sub.add_parser("export", help="write the Excel file")
    p.add_argument("--out", default="jword_leads.xlsx")
    p.set_defaults(fn=cmd_export)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
