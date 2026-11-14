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
    re.compile(r"\(with salaries\)|\bsalar(y|ies)\b|\bopen positions\b", re.I),
    re.compile(r"\b(vacancies|job openings|jobs and careers)\b", re.I),
    re.compile(r"^jobs?\s+(in|for)\b", re.I),
]
TRACKING_PARAMS = re.compile(r"^(utm_.*|trk.*|ref.*|src|source|from|fbclid|gclid|mc_.*|_hs.*|tk|cid|campaign.*)$", re.I)
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
}

QUERY_STYLES = [
    "{role} job {loc} hiring {month}",
    '"{role}" {loc} vacancy apply {year}',
    "{role} {loc} careers job opening {month}",
    "{role} jobs {loc} posted this week",
    '"{role}" {loc} "apply now" {year}',
]
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
MAX_AGE_DAYS = {"day": 2, "week": 10, "month": 35, "any": 0}

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

LEAD_COLUMNS = ["Date Added", "Mode", "Company", "Job Title", "Location", "Posted", "Source",
                "Job URL", "Fit Score", "Why It Fits", "Pitch / Tip", "Contact", "Contact Link",
                "Email", "Apply Via", "Status", "Next Step", "Run ID"]
CONTACT_COLUMNS = ["Company", "Name", "Role", "Email", "Type", "Found On", "Run ID"]
APPLICATION_COLUMNS = ["Date", "Company", "Job Title", "Job URL", "Apply Via", "Status", "Next Step",
                       "Cover Letter / Message", "Answers Used", "Run ID"]
RUNLOG_COLUMNS = ["Run ID", "Date", "Time", "Run By", "Mode", "Roles", "Locations", "Posted Within",
                  "Ranking", "Min Score", "Target", "Saved", "Saved By Source", "Low Fit", "Duplicates",
                  "Closed", "Wrong Location", "Agency", "Not A Job", "Page Checked", "Searches",
                  "Candidates Reviewed", "Emails Found", "Applied", "Emailed", "Needs You", "Status", "Notes"]

# ---- contacts & applying -------------------------------------------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
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


def out(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


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


DATE_RX = (r"([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{1,2}(?:st|nd|rd|th)? [A-Z][a-z]{2,8},? \d{4}"
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


def parse_age(text: str):
    """(days, text) from '3 days ago', 'Posted: 05.05.2025', 'Published Aug 20, 2026', 'yesterday'..."""
    t = str(text or "")
    m = re.search(r"(\d+)\+?\s*(minute|min|hour|hr|day|week|wk|month|mo|year|yr)s?\s+ago", t, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = (0 if unit.startswith(("minute", "min", "hour", "hr")) else n if unit.startswith("day")
                else n * 7 if unit.startswith(("week", "wk")) else n * 30 if unit.startswith(("month", "mo")) else n * 365)
        return days, m.group(0)
    m = re.search(r"\b(just now|today|just posted)\b", t, re.I)
    if m:
        return 0, m.group(0)
    m = re.search(r"\byesterday\b", t, re.I)
    if m:
        return 1, m.group(0)
    m = re.search(r"\b(?:posted|published|date posted|listed)[:\s]*(?:on\s+)?" + DATE_RX, t, re.I)
    if m and (d := parse_date(m.group(1))):
        return max(0, (dt.datetime.now() - d).days), m.group(1)
    return None


def closing_passed(text: str) -> bool:
    """True if the text shows a closing/expiry date that is already in the past."""
    m = re.search(r"\b(?:closes|closing date|closing|expires|expiry date|apply by|deadline)[:\s]*(?:on\s+)?" + DATE_RX,
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
    return "Generic" if local in GENERIC_LOCAL or any(x in GENERIC_LOCAL for x in parts) else "Person"


def apply_via(c: dict) -> str:
    """How this job is applied for (decides whether Claude may fill the form)."""
    d = domain_of(c["url"])
    if d in NO_AUTOMATION:
        return f"{NO_AUTOMATION[d]} (apply yourself)"
    if d in ATS:
        return ATS[d]
    if any(e["source"] == c["url"] for e in c.get("emails", [])) and re.search(r"\b(send|email) (your )?(cv|resume|application)", c.get("snippet", ""), re.I):
        return "Email"
    return "Company site"


def add_email(c: dict, email: str, source: str, name="", role="", from_posting=False) -> str:
    """Add one email to a lead. Returns '' if added, else the reason it was refused."""
    email = str(email or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return "not a valid email"
    if NOREPLY.match(email):
        return "no-reply address"
    if email.split("@")[1] in FREEMAIL and not from_posting:
        return "personal mailbox (only accepted when the job posting itself lists it)"
    if any(e["email"] == email for e in c.setdefault("emails", [])):
        return "already recorded"
    c["emails"].append({"email": email, "name": str(name or "").strip(), "role": str(role or "").strip(),
                        "type": email_type(email), "source": source})
    return ""


def best_email(c: dict) -> str:
    em = c.get("emails") or []
    if not em:
        return ""
    rank = lambda e: (0 if e["type"] == "Person" and re.search(r"recruit|talent|hr|people|hiring", e["role"] or "", re.I)
                      else 1 if e["type"] == "Generic" and re.match(r"(careers?|jobs?|hr|recruit|talent|hiring|people|apply)", e["email"])
                      else 2 if e["type"] == "Person" else 3)
    return sorted(em, key=rank)[0]["email"]


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
    for sheet, key in (("Leads", "leads"), ("Run Log", "runlog"), ("Contacts", "contacts"), ("Applications", "applications")):
        ws = wb[sheet] if sheet in wb.sheetnames else (wb.worksheets[0] if key == "leads" else None)
        if ws is None:
            continue
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = [str(h or "").strip() for h in rows[0]]
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
                if c.get("key") and c.get("status") in ("saved", "surplus", "ready") + IN_FLIGHT)
    return keys


def source_cap(st) -> int:
    """Most leads one website may supply, so results stay varied (lifted when nothing else is left)."""
    return max(2, math.ceil(st["config"]["target"] / 3))


def source_load(st, src) -> int:
    return sum(1 for c in st["candidates"] if c["source"] == src and c["status"] in ("saved",) + IN_FLIGHT)


# ============================================================================ outcomes


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
        c["open_check"] = "Snippet only" if cfg["verify_open"] else "Not checked"
    if cfg["mode"] == "clients" and cfg["agencies"] == "skip" and not str(c.get("company") or "").strip():
        miss(st, c, "agency", "employer not named")      # a client lead needs a named company
        return
    if cfg["mode"] == "clients" and cfg["find_contacts"] and c.get("company") and c.get("contact") is None:
        c["status"] = "needs_contact"
        return
    save_lead(st, c)


def save_lead(st, c):
    if st["saved"] >= st["config"]["target"]:
        c["status"] = "surplus"
        return
    c["status"] = "saved"
    c["saved_at"] = dt.datetime.now().isoformat(timespec="seconds")
    st["saved"] += 1
    st["saved_by_source"][c["source"]] = st["saved_by_source"].get(c["source"], 0) + 1
    st["consecutive_misses"] = 0


def promote(st, final=False):
    """Release qualified ('ready') leads, best score first, within the per-source cap
    (final=True ignores the cap so the target can still be met when sources are scarce)."""
    target = st["config"]["target"]
    cap = source_cap(st)
    while True:
        busy = sum(1 for c in st["candidates"] if c["status"] in IN_FLIGHT)
        if st["saved"] + busy >= target:
            return
        ready = [c for c in st["candidates"] if c["status"] == "ready"]
        pick = [c for c in ready if final or source_load(st, c["source"]) < cap]
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
    st = {
        "version": 2,
        "run_id": "jw-" + now.strftime("%Y%m%d-%H%M%S"),
        "started_at": now.isoformat(timespec="seconds"),
        "config": {
            "mode": args.mode, "roles": roles, "locations": locations, "offer": args.offer or "",
            "ranking": args.ranking, "min_score": int(args.min_score), "posted": args.posted,
            "verify_open": args.verify_open == "yes", "find_contacts": args.find_contacts == "yes",
            "strict_location": args.location_filter == "strict", "agencies": agencies,
            "platforms": platforms, "platforms_only": bool(args.platforms_only and platforms),
            "target": target, "run_by": args.run_by or "",
            "max_searches": min(40, target * 2 + len(roles) * len(locations) + 2),
            "max_misses": max(30, target * 4),
        },
        "saved": 0, "saved_by_source": {}, "searches": 0, "query_index": 0, "consecutive_misses": 0,
        "counts": {}, "candidates": [], "pending_search": None, "status": "running", "notes": [],
        "known_urls": [], "known_keys": [], "existing": {"leads": [], "runlog": [], "contacts": [], "applications": []},
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
    save(args, st)
    out({"ok": True, "run_id": st["run_id"], "config": st["config"],
         "existing_leads_loaded": len(st["existing"]["leads"]),
         "next": "Run `jword.py next` to get the first step."})


def build_query(st) -> dict:
    cfg = st["config"]
    i = st["query_index"]
    combos = [(r, l) for r in cfg["roles"] for l in cfg["locations"]]
    role, loc = combos[i % len(combos)]
    style = QUERY_STYLES[(i // len(combos)) % len(QUERY_STYLES)]
    now = dt.datetime.now()
    loc_txt = "" if is_anywhere(loc) else ("remote" if is_remote(loc) else loc)
    if st["consecutive_misses"] >= 15:          # stuck: plainest wording
        style = "{role} job {loc} {year}"
    query = style.format(role=role, loc=loc_txt, month=now.strftime("%B %Y"), year=now.year)
    plats = cfg.get("platforms") or []
    if plats and (i % 2 == 1 or cfg.get("platforms_only")):      # steer every other search toward a chosen platform
        query += " " + PLATFORMS[plats[(i // 2) % len(plats)]][0]
    return {"role": role, "location": loc, "query": re.sub(r"\s+", " ", query).strip()}


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
    out_of_luck = st["consecutive_misses"] >= cfg["max_misses"]
    # Variety vs. cost: after a few searches, if enough qualified leads are already waiting,
    # let them through even if one website supplies more than its share.
    waiting = sum(1 for c in st["candidates"] if c["status"] in ("ready",) + IN_FLIGHT)
    enough = st["searches"] >= 4 and st["saved"] + waiting >= cfg["target"]
    promote(st, final=out_of_searches or out_of_luck or enough)
    if st["saved"] >= cfg["target"]:
        return done("target_reached", "Target number of leads saved.")

    # 1) follow-ups (page checks / contact lookups) on qualified leads
    follow = [c for c in st["candidates"] if c["status"] in IN_FLIGHT]
    if follow:
        tasks = []
        for c in follow[:5]:
            if c["status"] == "needs_open_check":
                tasks.append({"id": c["id"], "type": "open_check", "url": c["url"], "company": c.get("company"),
                              "role": c.get("role"),
                              "how": "web_fetch the URL. Reply {id, open: true|false|null, posted: '<age/date if shown>'"
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
        cap = source_cap(st)
        fresh = [c for c in queued if source_load(st, c["source"]) < cap] or queued
        fresh.sort(key=lambda c: (not on_platform(cfg, c), -(c.get("keyword_score") or 0)))
        batch, per_src = [], {}
        for c in fresh:                                   # at most 2 per source in one batch
            if per_src.get(c["source"], 0) < 2:
                batch.append(c)
                per_src[c["source"]] = per_src.get(c["source"], 0) + 1
            if len(batch) >= REVIEW_BATCH:
                break
        save(args, st)
        return out({
            "action": "review",
            "instructions": "Score each candidate with references/scoring-rubric.md. Reply with a JSON list of "
                            "{id, is_job_posting, is_open, is_agency, company, role, location, fit_score (1-5), "
                            "fit_reason, angle} then run `jword.py apply --updates <file>`.",
            "mode": cfg["mode"], "offer": cfg["offer"], "roles": cfg["roles"], "locations": cfg["locations"],
            "candidates": [{"id": c["id"], "source": c["source"], "url": c["url"], "title": c["title"],
                            "snippet": c["snippet"], "posted": c.get("posted", "")} for c in batch],
        })

    if out_of_luck:
        return done("retry_limit_reached", f"{cfg['max_misses']} results in a row did not produce a lead.")
    if out_of_searches:
        return done("max_searches_reached", f"Used the search budget ({cfg['max_searches']} searches).")

    # 3) search
    plan = build_query(st)
    st["pending_search"] = plan
    save(args, st)
    out({"action": "search", **plan,
         "next": "web_search this exact query. Save ALL results as a JSON list of {title, url, snippet} "
                 "(snippet = the text shown for that result, including any '3 days ago' / 'Posted …' / 'Closes …' "
                 "text) and run `jword.py ingest --results <file>`. If the search fails, ingest []."})


def cmd_ingest(args):
    st = load(args)
    cfg = st["config"]
    if not st.get("pending_search"):
        fail("No search is pending. Run `jword.py next` first.")
    try:
        results = json.loads(Path(args.results).read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Could not read results JSON: {e}")
    if isinstance(results, dict):
        results = results.get("results") or results.get("web") or results.get("data") or []

    st["searches"] += 1
    st["query_index"] += 1
    st["pending_search"] = None
    matcher = LocationMatcher(cfg["locations"])
    max_age = MAX_AGE_DAYS[cfg["posted"]]
    seen, keys = known_urls(st), known_keys(st)
    stats = {k: 0 for k in ("results", "new", "listing_or_irrelevant", "already_seen", "closed_or_stale",
                            "duplicate", "wrong_location", "agency", "low_fit", "queued_for_review", "qualified")}
    stats["results"] = len(results)
    role_words = {w for r in cfg["roles"] for w in (words(r) or [r.lower()])}

    for r in results:
        url = str(r.get("url") or r.get("link") or "").strip()
        title = str(r.get("title") or "").strip()
        snippet = re.sub(r"\s+", " ", str(r.get("snippet") or r.get("description") or "")).strip()
        text = f"{title} {snippet}"
        if (not url.startswith("http") or any(d in url.lower() for d in EXCLUDED_DOMAINS)
                or is_listing(title, url) or not any(w in text.lower() for w in role_words)):
            stats["listing_or_irrelevant"] += 1
            continue
        nurl = normalize_job_url(url)
        if nurl in seen:
            stats["already_seen"] += 1
            continue
        seen.add(nurl)
        age = parse_age(snippet) or parse_age(title)
        if CLOSED_RE.search(text) or closing_passed(snippet) or (age and max_age and age[0] > max_age):
            stats["closed_or_stale"] += 1
            st["counts"]["closed"] = st["counts"].get("closed", 0) + 1
            continue

        p = parse_title(title, url)
        c = {"id": f"c{len(st['candidates']) + 1}", "source": source_of(nurl), "url": display_url(url), "nurl": nurl, "title": title,
             "snippet": snippet[:700], "company": p["company"], "role": p["role"], "location": p["location"],
             "posted": age[1] if age else "", "status": "new", "open_check": None, "contact": None}
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

    if stats["new"] == 0:
        st["consecutive_misses"] += 1
    save(args, st)
    out({"ok": True, "stats": stats, "saved": st["saved"], "target": cfg["target"], "next": "Run `jword.py next`."})


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
    max_age = MAX_AGE_DAYS[cfg["posted"]]
    results, errors = [], []

    for u in updates:
        c = cand(st, str(u.get("id", "")))
        if not c:
            errors.append(f"unknown id {u.get('id')}")
            continue
        if "fit_score" in u or "is_job_posting" in u:                     # --- verdict
            if c["status"] != "queued":
                errors.append(f"{c['id']}: not waiting for a verdict (status {c['status']})")
                continue
            for f in ("company", "role", "location"):
                v = str(u.get(f) or "").strip()
                if v:
                    c[f] = v
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
        elif "open" in u or "page_text" in u:                              # --- page check
            if c["status"] != "needs_open_check":
                errors.append(f"{c['id']}: no page check pending")
                continue
            st["counts"]["page_checked"] = st["counts"].get("page_checked", 0) + 1
            is_open = u.get("open")
            text = str(u.get("page_text") or "")[:4000]
            posted = str(u.get("posted") or "").strip()
            age = parse_age(posted) or parse_age(text)
            if not age and (d := parse_date(posted)):
                age = (max(0, (dt.datetime.now() - d).days), posted)
            if text and (CLOSED_RE.search(text) or closing_passed(text)):
                is_open = False
            if is_open is False:
                miss(st, c, "closed", "page check")
            elif age and max_age and age[0] > max_age:
                miss(st, c, "closed", f"stale ({age[1]})")
            else:
                for f in ("company", "role", "location"):          # the page often names the employer
                    v = str(u.get(f) or "").strip()
                    if v and not str(c.get(f) or "").strip():
                        c[f] = v
                if u.get("company") and not c.get("key"):
                    c["key"] = dedupe_key(cfg["mode"], c["company"], c["role"])
                for f, k in (("fit_reason", "fit_reason"), ("angle", "angle")):   # refreshed after reading the page
                    v = str(u.get(f) or "").strip()
                    if v:
                        c[k] = v
                c["open_check"] = "Open (page checked)" if is_open else "Unverified (page check failed)"
                if not c.get("posted") and (age or posted):
                    c["posted"] = age[1] if age else posted
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
    out({"ok": not errors, "applied": results, "errors": errors, "saved": st["saved"],
         "target": cfg["target"], "next": "Run `jword.py next`."})


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


def cmd_plan(args):
    st = load(args)
    cfg = st["config"]
    leads = []
    for c in saved_leads(st):
        status, nxt = lead_status(st, c)
        d = domain_of(c["url"])
        site = c.get("website") or (d if d not in ATS and d not in NO_AUTOMATION and c["source"] == d else "")
        leads.append({"id": c["id"], "company": c.get("company"), "role": c.get("role"), "url": c["url"],
                      "apply_via": apply_via(c), "website": site, "emails": [e["email"] for e in c.get("emails", [])],
                      "contacts_checked": bool(c.get("contacts_checked")), "status": status, "next_step": nxt})
    out({"mode": cfg["mode"], "leads": leads,
         "todo": {"contacts": [l["id"] for l in leads if not l["contacts_checked"]],
                  "to_apply": [l["id"] for l in leads if cfg["mode"] == "jobs" and l["status"] in ("To apply", "Prepared")],
                  "to_email": [l["id"] for l in leads if l["emails"] and l["status"] in ("New", "To apply", "Prepared")]},
         "next": "Follow SKILL.md step 5 (ask the user what to do next), then references/contacts.md, "
                 "references/applying.md or references/outreach.md."})


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
    added, refused = [], []
    for u in updates:
        c = cand(st, str(u.get("id", "")))
        if not c or c["status"] != "saved":
            refused.append({"id": u.get("id"), "why": "unknown or unsaved lead"})
            continue
        if u.get("website"):
            c["website"] = domain_of(str(u["website"])) or str(u["website"])
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
        c["contacts_checked"] = True
    save(args, st)
    out({"ok": True, "added": added, "refused": refused, "next": "Run `jword.py plan` to see what's left."})


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


def cmd_profile_check(args):
    p = Path(args.profile)
    if not p.exists():
        fail(f"Profile not found: {p}. Create it from references/applicant-profile.md.")
    try:
        prof = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        fail(f"Profile is not valid JSON: {e}")
    missing = [k for k in PROFILE_REQUIRED if prof.get(k) in (None, "", [], {})]
    cv = str(prof.get("cv_path") or "").strip()
    has_cv = bool(cv) and Path(cv).exists()
    if not (has_cv or (prof.get("experience") and prof.get("skills"))):
        missing.append("cv_path (a CV file) or experience + skills")
    out({"ok": not missing, "missing": missing, "cv_file": cv if has_cv else "",
         "cv_upload_note": "" if has_cv else "No CV file: forms that require an upload will be marked 'Needs you: upload CV'.",
         "eeo": prof.get("eeo_answers", "ask"),
         "next": "Ask the user for the missing fields (one message), save them, and run profile-check again."
                 if missing else "Profile is ready for applying."})


def cmd_report(args):
    """Markdown status list for the end of the chat."""
    st = load(args)
    rows = []
    for i, c in enumerate(saved_leads(st), 1):
        status, nxt = lead_status(st, c)
        email = best_email(c) or "-"
        rows.append(f"| {i} | {c.get('company') or '?'} | [{c.get('role') or 'Job'}]({c['url']}) | {c.get('fit_score') or '-'} "
                    f"| {apply_via(c)} | {email} | **{status}** | {nxt or '-'} |")
    counts = {}
    for c in saved_leads(st):
        s_, _ = lead_status(st, c)
        counts[s_] = counts.get(s_, 0) + 1
    head = "| # | Company | Job | Fit | Apply via | Email | Status | Next step |\n|---|---|---|---|---|---|---|---|"
    out({"markdown": head + "\n" + "\n".join(rows), "totals": counts})


def summary(st) -> dict:
    cfg, cnt = st["config"], st["counts"]
    return {
        "run_id": st["run_id"], "status": st["status"], "saved": st["saved"], "target": cfg["target"],
        "saved_by_source": st["saved_by_source"], "searches": st["searches"], "max_searches": cfg["max_searches"],
        "skipped": {k: cnt.get(k, 0) for k in ("low_fit", "duplicate", "closed", "wrong_location", "agency", "not_job")},
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

    new_rows = []
    for c in sorted((c for c in st["candidates"] if c["status"] == "saved"), key=lambda c: c.get("saved_at", "")):
        ct = c.get("contact") or {}
        contact = ct.get("name", "")
        if contact and ct.get("title"):
            contact = f"{contact} ({ct['title']})"
        new_rows.append({
            "Date Added": (c.get("saved_at") or now.isoformat())[:10], "Mode": mode_label,
            "Company": c.get("company", ""), "Job Title": c.get("role", ""), "Location": c.get("location", ""),
            "Posted": c.get("posted", ""), "Source": c["source"], "Job URL": c["url"],
            "Fit Score": c.get("fit_score") if c.get("fit_score") is not None else "",
            "Why It Fits": c.get("fit_reason", ""), "Pitch / Tip": c.get("angle", ""),
            "Contact": contact, "Contact Link": ct.get("url", ""),
            "Email": best_email(c), "Apply Via": apply_via(c) if cfg["mode"] == "jobs" else "",
            "Status": lead_status(st, c)[0], "Next Step": lead_status(st, c)[1], "Run ID": st["run_id"],
        })
    new_contacts, new_apps = [], []
    for c in saved_leads(st):
        for e in c.get("emails", []):
            new_contacts.append({"Company": c.get("company", ""), "Name": e["name"], "Role": e["role"], "Email": e["email"],
                                 "Type": e["type"], "Found On": e["source"], "Run ID": st["run_id"]})
        a = c.get("application") or {}
        if a.get("status"):
            new_apps.append({"Date": (a.get("done_at") or a.get("updated_at") or "")[:10], "Company": c.get("company", ""),
                             "Job Title": c.get("role", ""), "Job URL": c["url"], "Apply Via": a.get("method") or apply_via(c),
                             "Status": JOB_STATUSES.get(a["status"], a["status"]), "Next Step": a.get("next_step", ""),
                             "Cover Letter / Message": a.get("message", ""), "Answers Used": a.get("answers", ""),
                             "Run ID": st["run_id"]})

    cnt = st["counts"]
    run_row = {
        "Run ID": st["run_id"], "Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"),
        "Run By": cfg["run_by"], "Mode": mode_label, "Roles": ", ".join(cfg["roles"]),
        "Locations": ", ".join(cfg["locations"]) + ("" if cfg["strict_location"] else " (not filtered)"),
        "Posted Within": {"day": "Past 24 hours", "week": "Past week", "month": "Past month", "any": "Any time"}[cfg["posted"]],
        "Ranking": {"ai": "AI (Claude)", "keyword": "Keyword", "none": "None"}[cfg["ranking"]],
        "Min Score": "" if cfg["ranking"] == "none" else cfg["min_score"], "Target": cfg["target"],
        "Saved": st["saved"],
        "Saved By Source": ", ".join(f"{k}: {v}" for k, v in sorted(st["saved_by_source"].items(), key=lambda x: -x[1])),
        "Low Fit": cnt.get("low_fit", 0), "Duplicates": cnt.get("duplicate", 0), "Closed": cnt.get("closed", 0),
        "Wrong Location": cnt.get("wrong_location", 0), "Agency": cnt.get("agency", 0),
        "Not A Job": cnt.get("not_job", 0), "Page Checked": cnt.get("page_checked", 0),
        "Searches": st["searches"], "Candidates Reviewed": len(st["candidates"]),
        "Emails Found": len(new_contacts),
        "Applied": sum(1 for a in new_apps if a["Status"] == "Applied"),
        "Emailed": sum(1 for a in new_apps if a["Status"] == "Emailed"),
        "Needs You": sum(1 for a in new_apps if a["Status"] == "Needs you"), "Status": st["status"],
        "Notes": "; ".join(st["notes"]),
    }

    leads = [{**r, "Source": r.get("Source") or r.get("Job Board", ""), "Email": r.get("Email", ""),
              "Contact Link": r.get("Contact Link") or r.get("Contact LinkedIn", "")}
             for r in st["existing"]["leads"]] + new_rows
    runlog = list(st["existing"]["runlog"]) + [run_row]
    contacts = list(st["existing"].get("contacts", [])) + new_contacts
    apps = list(st["existing"].get("applications", [])) + new_apps

    wb = openpyxl.Workbook()
    head_fill = PatternFill("solid", start_color="1F3864")
    head_font = Font(name="Arial", bold=True, color="FFFFFF")
    body_font = Font(name="Arial", size=10)
    link_font = Font(name="Arial", size=10, color="0563C1", underline="single")
    score_fill = {5: "C6EFCE", 4: "E2EFDA", 3: "FFF2CC", 2: "FCE4D6", 1: "F8CBAD"}
    widths = {"Company": 24, "Job Title": 30, "Location": 22, "Source": 16, "Job URL": 40, "Why It Fits": 48,
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
                cell.alignment = Alignment(vertical="top", wrap_text=col in ("Why It Fits", "Pitch / Tip", "Notes", "Next Step",
                                                                             "Cover Letter / Message", "Answers Used"))
                if col in ("Job URL", "Contact Link", "Found On") and str(cell.value or "").startswith("http"):
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
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    wb.save(outp)
    save(args, st)
    out({"ok": True, "file": str(outp), "new_leads": len(new_rows), "total_leads": len(leads),
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
    p.add_argument("--posted", choices=list(MAX_AGE_DAYS), default="week")
    p.add_argument("--verify-open", choices=["yes", "no"], default="yes")
    p.add_argument("--find-contacts", choices=["yes", "no"], default="yes")
    p.add_argument("--location-filter", choices=["strict", "keep-all"], default="strict")
    p.add_argument("--agencies", choices=["skip", "keep"], default="", help="recruitment-agency posts (default: skip in clients mode)")
    p.add_argument("--platforms", default="", help=f"preferred platforms, comma-separated: {', '.join(PLATFORMS)}")
    p.add_argument("--platforms-only", action="store_true", help="keep only results from --platforms")
    p.add_argument("--target", default=10)
    p.add_argument("--run-by", default="")
    p.add_argument("--existing", default="", help="earlier Jword .xlsx/.csv: skip its leads and append to it on export")
    p.set_defaults(fn=cmd_init)

    sub.add_parser("next", help="what to do next").set_defaults(fn=cmd_next)
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
    sub.add_parser("report", help="final status list (markdown)").set_defaults(fn=cmd_report)
    p = sub.add_parser("export", help="write the Excel file")
    p.add_argument("--out", default="jword_leads.xlsx")
    p.set_defaults(fn=cmd_export)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
