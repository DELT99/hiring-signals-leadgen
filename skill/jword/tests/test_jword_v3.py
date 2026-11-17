#!/usr/bin/env python3
"""Tests for Jword v3: strict posting window, contact verification, outreach, Gmail logging,
repeated runs and parallel work packets.   Run:  python3 tests/test_jword_v3.py"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import jword as J  # noqa: E402
from test_jword import run, drive, export  # noqa: E402

TESTS = []
T0 = dt.date.today()


def test(fn):
    TESTS.append(fn)
    return fn


def res(n, snippet, co=None, role="Flutter Developer"):
    co = co or f"Co{n}"
    return {"title": f"{role} at {co}", "url": f"https://jobs.lever.co/{co.lower()}/{n:08x}-aaaa", "snippet": snippet}


JOBS = ["init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Remote",
        "--offer", "Flutter and Dart developer, 2 years, Firebase", "--ranking", "keyword", "--verify-open", "no"]


def fixed(results):
    """Same results for every search (URLs are de-duplicated after the first)."""
    return lambda q, n: results if n == 0 else []


# ------------------------------------------------------------------ window parsing

@test
def window_presets_and_natural_language():
    w = lambda s: J.parse_window(s, dt.date(2026, 11, 15))
    assert w("24h")["start"] == "2026-11-14" and w("3d")["start"] == "2026-11-12"
    assert w("7d")["start"] == "2026-11-08" and w("14d")["start"] == "2026-11-01"
    assert w("30d")["start"] == "2026-10-16" and w("60d")["start"] == "2026-09-16"
    assert w("Jobs posted within the last 10 days")["start"] == "2026-11-05"
    assert w("this week")["start"] == "2026-11-09"
    r = w("between November 1 and November 10")
    assert (r["start"], r["end"]) == ("2026-11-01", "2026-11-10")
    assert w("2026-11-01..2026-11-10")["end"] == "2026-11-10" and w("since Nov 3")["start"] == "2026-11-03"
    assert w("any") is None and w("week")["start"] == "2026-11-08"       # legacy value
    with tempfile.TemporaryDirectory() as tmp:
        assert "error" in run(tmp, *JOBS, "--posted-within", "soonish", ok=False)


@test
def original_vs_updated_dates():
    T = dt.date(2026, 11, 15)
    w14 = J.parse_window("14d", T)
    e = J.estimate_posting("Updated 2 days ago · Posted 20 days ago", T)
    assert e["kind"] == "posted" and e["min"] == 20 and J.window_verdict(e, w14, T) == "out"
    e = J.estimate_posting("Reposted 3 days ago", T)
    assert e["kind"] == "updated" and J.window_verdict(e, w14, T) == "unclear"     # original date unknown
    e = J.estimate_posting("Reviewed: Thu, Sep 17, 2026", T)
    assert e["kind"] == "updated" and J.window_verdict(e, w14, T) == "out"          # at least that old
    e = J.estimate_posting('{"datePosted": "2026-11-12", "dateModified": "2026-11-14"}', T)
    assert e["min"] == 3 and J.window_verdict(e, w14, T) == "in"
    assert J.window_verdict(J.estimate_posting("2 weeks ago", T), w14, T) == "unclear"   # 14-20 days
    assert J.window_verdict(J.estimate_posting("1 week ago", T), w14, T) == "in"
    e = J.estimate_posting("Listing details: First seen June 16, 2026", T)
    assert e["kind"] == "updated" and J.window_verdict(e, w14, T) == "out"
    e = J.estimate_posting("Flutter Developer. Lahore. Pay 80,000. Similar jobs Sadeema Egypt about 1 hour ago", T)
    assert e is None                                     # sidebar dates belong to other jobs
    e = J.estimate_posting("AI Engineer. Date: 2 weeks ago. City: Lahore. Similar jobs Contegris 2 days ago", T)
    assert e["min"] == 14
    for x, n in (("Posted 2d ago", 2), ("Posted a day ago", 1), ("1 day, 2 hours ago", 1), ("Posted YDay", 1),
                 ("Date: 6 hours ago", 0), ("about 2 months ago", 56)):
        assert J.estimate_posting(x, T)["min"] == n, x
    assert J.estimate_posting("Active 2 days ago", T)["kind"] == "updated"
    assert J.estimate_posting("Ali Khan · HR Manager 2d • We're hiring Flutter devs", T)["min"] == 2
    assert J.estimate_posting("AI Engineer. Posting Date: Nov 07, 2026. Similar Job Titles AI Engineer Posted Nov 15, 2026", T)["min"] == 8
    assert J.window_verdict(J.estimate_posting("Posted last year", T), w14, T) == "out"
    assert J.closing_passed("Applications will be accepted until March 8, 2026.") and J.closing_passed("Apply before Apr 6, 2025")
    assert J.window_verdict(None, w14, T) == "unclear" and J.window_verdict(None, None, T) == "in"


# ------------------------------------------------------------------ strict filter in runs

@test
def strict_window_excludes_undated_and_old_never_relaxes():
    results = [res(1, "Posted 2 days ago. Remote. Flutter Dart Firebase."),
               res(2, "Remote. Flutter Dart role, no date shown."),
               res(3, "Posted 3 weeks ago. Remote Flutter Dart."),
               res(4, "Reposted 1 day ago. Remote Flutter Dart."),
               res(5, "Posted 1 day ago. Remote Flutter Dart Firebase.")]
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *JOBS, "--posted-within", "7d", "--target", "10")
        nxt, _ = drive(tmp, results_fn=fixed(results))
        assert nxt["saved"] == 2, nxt                   # target 10 not met, and the window was not widened
        _, (leads, _), (log, _) = export(tmp)
        assert sorted(l["Company"] for l in leads) == ["Co1", "Co5"]
        assert all(l["Posting Window"].startswith("Last 7 days") and "date in window" in l["Verification"] for l in leads)
        assert log[0]["Outside Window"] == 1 and log[0]["No Date"] == 2, log[0]
        import openpyxl
        wb = openpyxl.load_workbook(Path(tmp) / "leads.xlsx")
        reasons = {r[3] for r in wb["Excluded"].iter_rows(min_row=2, values_only=True)}
        assert {"Posted outside the chosen window", "No verifiable posting date"} <= reasons, reasons


@test
def undated_listed_separately_when_allowed():
    results = [res(1, "Posted today. Remote Flutter Dart."), res(2, "Remote Flutter Dart, undated.")]
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *JOBS, "--posted-within", "3d", "--undated", "separate", "--target", "5")
        drive(tmp, results_fn=fixed(results))
        r = run(tmp, "export", "--out", str(Path(tmp) / "x.xlsx"))
        assert r["new_leads"] == 1 and r["undated"] == 1
        import openpyxl
        wb = openpyxl.load_workbook(r["file"])
        assert "Undated Jobs" in wb.sheetnames
        rep = run(tmp, "report")
        assert "Undated jobs" in rep["markdown"] and "Co2" in rep["markdown"]


@test
def last_24_hours_and_custom_range():
    today = dt.date.today()
    inside = (today - dt.timedelta(days=5)).strftime("%b %d, %Y")
    after = (today - dt.timedelta(days=1)).strftime("%b %d, %Y")
    rng = f"{(today - dt.timedelta(days=8)).isoformat()}..{(today - dt.timedelta(days=3)).isoformat()}"
    results = [res(1, f"Posted on {inside}. Remote Flutter Dart."), res(2, f"Posted on {after}. Remote Flutter Dart.")]
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *JOBS, "--posted-within", rng, "--target", "5")
        nxt, _ = drive(tmp, results_fn=fixed(results))
        assert nxt["saved"] == 1                         # the one posted after the range end is out
    results = [res(1, "5 hours ago · Remote Flutter Dart"), res(2, "2 days ago · Remote Flutter Dart")]
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *JOBS, "--posted-within", "24h", "--target", "5")
        nxt, _ = drive(tmp, results_fn=fixed(results))
        assert nxt["saved"] == 1


@test
def page_date_beats_snippet_and_updated_only_is_dropped():
    results = [res(1, "Posted 1 day ago. Remote Flutter Dart."), res(2, "Posted 2 days ago. Remote Flutter Dart."),
               res(3, "Remote Flutter Dart.")]
    pages = {"Co1": {"open": True, "posted": "Date posted: " + (T0 - dt.timedelta(days=40)).isoformat()},
             "Co2": {"open": True, "posted": "", "updated": "2 days ago"},
             "Co3": {"open": True, "posted": "3 days ago", "posted_source": "page header"}}
    with tempfile.TemporaryDirectory() as tmp:
        args = [a for a in JOBS if a not in ("--verify-open", "no")]
        run(tmp, *args, "--posted-within", "7d", "--target", "5")
        drive(tmp, results_fn=fixed(results), page_fn=lambda t: pages[t["company"]])
        _, (leads, _), (log, _) = export(tmp)
        assert [l["Company"] for l in leads] == ["Co3"] and leads[0]["Date Source"].startswith("job page")
        assert log[0]["Outside Window"] == 1 and log[0]["No Date"] == 1


# ------------------------------------------------------------------ contacts

def saved_run(tmp, n=3, mode="jobs"):
    results = [res(i, f"Posted 1 day ago. Remote Flutter Dart Firebase. Team {i}.", co=f"Firm{i}") for i in range(1, n + 1)]
    base = JOBS if mode == "jobs" else ["init", "--mode", "clients", "--roles", "Flutter Developer", "--locations", "Remote",
                                         "--offer", "Flutter agency", "--ranking", "keyword", "--verify-open", "no",
                                         "--find-contacts", "no"]
    run(tmp, *base, "--posted-within", "7d", "--target", str(n))
    drive(tmp, results_fn=fixed(results))
    return [l["id"] for l in run(tmp, "plan")["leads"]]


def write(tmp, name, obj):
    f = Path(tmp) / name
    f.write_text(json.dumps(obj))
    return str(f)


@test
def contact_types_verification_and_dedupe():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = saved_run(tmp)
        r = run(tmp, "contacts", "--updates", write(tmp, "c.json", [
            {"id": a, "website": "https://firm1.com", "emails": [
                {"email": "careers@firm1.com", "source_url": "https://firm1.com/careers", "evidence": "Email careers@firm1.com"},
                {"email": "ana.k@firm1.com", "name": "Ana K", "role": "Talent Acquisition", "source_url": "https://firm1.com/team",
                 "evidence": "Ana K, Talent Acquisition - ana.k@firm1.com"},
                {"email": "jobs@firm1.com", "source_url": "https://randomjobsite.net/x", "evidence": "contact jobs@firm1.com"},
                {"email": "nope@firm1", "source_url": "https://firm1.com", "evidence": "nope@firm1"},
                {"email": "guess@firm1.com", "source_url": "https://firm1.com", "evidence": "no address here"},
                {"email": "x@firm1.com", "source_url": "", "evidence": "x@firm1.com"}],
             "people": [{"name": "Omar Q", "role": "Founder", "source_url": "https://firm1.com/about", "evidence": "Founded by Omar Q"}]},
            {"id": b, "emails": [{"email": "hr@third.io", "source_url": "https://blog.example.net/post", "evidence": "hr@third.io"}]}]))
        assert {x["email"] for x in r["added"] if "email" in x} == {"careers@firm1.com", "ana.k@firm1.com", "jobs@firm1.com", "hr@third.io"}
        assert len(r["refused"]) == 3
        plan = {l["id"]: l for l in run(tmp, "plan")["leads"]}
        assert set(plan[a]["emails"]) == {"careers@firm1.com", "ana.k@firm1.com"}
        assert plan[a]["unverified_emails"] == ["jobs@firm1.com"] and plan[b]["emails"] == []
        res_, _, _ = export(tmp)
        import openpyxl
        rows = list(openpyxl.load_workbook(res_["file"])["Contacts"].iter_rows(values_only=True))
        hdr = rows[0]
        d = [dict(zip(hdr, r)) for r in rows[1:]]
        ana = next(x for x in d if x["Email"] == "ana.k@firm1.com")
        assert ana["Type"] == "Named" and ana["Role"] == "Talent Acquisition" and ana["Verification"] == "Verified: company website"
        assert next(x for x in d if x["Email"] == "jobs@firm1.com")["Verification"].startswith("Unverified")
        assert any(x["Name"] == "Omar Q" and x["Email"] == "(no public email)" for x in d)


@test
def job_board_is_not_the_company_site():
    c = {"company": "Bricks Tech", "url": "https://jobs.taraki.co/jobs/ai-engineer-bricks-tech"}
    assert not J.looks_like_company_site(c, "taraki.co") and J.looks_like_company_site(c, "brickstech.com")
    assert J.looks_like_company_site({"company": "Abyan Capital"}, "abyan-capital.breezy.hr".split(".")[0] + ".com")
    with tempfile.TemporaryDirectory() as tmp:
        a, _, _ = saved_run(tmp)
        st = json.loads((Path(tmp) / "state.json").read_text())
        url = next(x["url"] for x in st["candidates"] if x["id"] == a)
        r = run(tmp, "contacts", "--updates", write(tmp, "c.json", [{"id": a, "website": url, "emails": [
            {"email": "support@lever.co", "source_url": url, "evidence": "help: support@lever.co"}]}]))
        assert any("job board" in x["why"] for x in r["refused"])


@test
def same_email_for_two_jobs_is_one_contact_row():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, _ = saved_run(tmp)
        ev = {"email": "careers@group.com", "source_url": "https://group.com/jobs", "evidence": "careers@group.com"}
        run(tmp, "contacts", "--updates", write(tmp, "c.json", [{"id": a, "emails": [ev]}, {"id": b, "emails": [ev]}]))
        st = json.loads((Path(tmp) / "state.json").read_text())
        for cnd in st["candidates"]:                       # make both leads the same company
            if cnd["id"] in (a, b):
                cnd["company"] = "Group"
        (Path(tmp) / "state.json").write_text(json.dumps(st))
        res_, _, _ = export(tmp)
        import openpyxl
        rows = list(openpyxl.load_workbook(res_["file"])["Contacts"].iter_rows(values_only=True))
        hits = [r for r in rows[1:] if r[3] == "careers@group.com"]
        assert len(hits) == 1 and hits[0][7].count("lever.co") == 2


# ------------------------------------------------------------------ outreach + Gmail

def body(company, extra):
    return (f"Hi there,\n\nI saw the Flutter Developer opening at {company} and wanted to reach out directly. {extra} "
            "I have two years of Flutter and Dart work, shipped Firebase-backed apps, and I enjoy owning features end to end. "
            "My CV is attached, and I would be glad to walk you through a recent app if that helps.\n\nBest regards,\nTalha")


def with_contacts(tmp, mode="jobs"):
    ids = saved_run(tmp, 3, mode)
    ups = [{"id": i, "website": f"firm{k}.com", "emails": [
        {"email": f"careers@firm{k}.com", "source_url": f"https://firm{k}.com/careers", "evidence": f"careers@firm{k}.com"},
        {"email": f"jobs@firm{k}.com", "source_url": "https://aggregator.biz/x", "evidence": f"jobs@firm{k}.com"}]}
           for k, i in enumerate(ids, 1)]
    run(tmp, "contacts", "--updates", write(tmp, "c.json", ups))
    return ids


@test
def outreach_validation_rules():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = with_contacts(tmp)
        run(tmp, "settings", "--email-mode", "drafts")
        r = run(tmp, "outreach", "--updates", write(tmp, "o.json", [
            {"id": a, "to": "careers@firm1.com", "subject": "Flutter Developer application - Talha",
             "body": body("Firm1", "Your offline-first approach to field apps is close to what I built for clinics.")},
            {"id": b, "to": "careers@firm2.com", "subject": "Flutter Developer application - Talha",
             "body": body("Firm2", "Your real-time chat product matches my socket work.")},
            {"id": b, "to": "jobs@firm2.com", "subject": "Firm2 Flutter role", "body": body("Firm2", "x")},
            {"id": c, "to": "boss@firm3.com", "subject": "Hello", "body": body("Firm3", "y")},
            {"id": c, "to": "careers@firm3.com", "subject": "Firm3 Flutter opening", "body": "Hi [Name], short."},
            {"id": c, "to": "careers@firm3.com", "subject": "Applying for Flutter at Firm3",
             "body": body("Firm3", "[insert company detail]")}]), ok=False)
        why = {(x["to"]): x["why"] for x in r["refused"]}
        assert len(r["accepted"]) == 1 and r["accepted"][0]["to"] == "careers@firm1.com"
        assert "same subject" in why["careers@firm2.com"]
        assert "not verified" in why["jobs@firm2.com"] and "never guess" in why["boss@firm3.com"]
        assert "placeholder" in why["careers@firm3.com"]
        r = run(tmp, "outreach", "--updates", write(tmp, "o2.json", [
            {"id": b, "to": "careers@firm2.com", "subject": "Firm2 Flutter Developer - Talha",
             "body": body("Firm2", "Your offline-first approach to field apps is close to what I built for clinics.")}]), ok=False)
        assert "identical" in r["refused"][0]["why"]            # copy-paste of the Firm1 email
        r = run(tmp, "outreach", "--updates", write(tmp, "o3.json", [
            {"id": a, "to": "careers@firm1.com", "subject": "Again", "body": body("Firm1", "Second go at it today.")}]), ok=False)
        assert "already contacted" in r["refused"][0]["why"]


@test
def gmail_modes_and_confirmation():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = with_contacts(tmp)
        texts = {a: "Your clinic scheduling app is close to my Firebase booking work.",
                 b: "Your logistics tracker needs the offline maps I have built before.",
                 c: "Your fitness app's animations are the kind of UI work I like most."}
        subj = {a: "Flutter role at Firm1", b: "Firm2: Flutter Developer application", c: "Application: Flutter at Firm3"}
        for k, i in enumerate((a, b, c), 1):
            run(tmp, "outreach", "--updates", write(tmp, f"o{i}.json", [
                {"id": i, "to": f"careers@firm{k}.com", "subject": subj[i], "body": body(f"Firm{k}", texts[i])}]))
        run(tmp, "settings", "--email-mode", "drafts")
        g = lambda name, obj, ok=True: run(tmp, "gmail", "--updates", write(tmp, name, obj), ok=ok)
        assert "policy violation" in g("g1.json", [{"oid": "o1", "action": "send", "ok": True, "id": "m1"}], ok=False)["refused"][0]["why"]
        g("g2.json", [{"oid": "o1", "action": "draft", "ok": True, "id": "r-111"}])
        r = g("g3.json", [{"oid": "o2", "action": "draft", "ok": True, "id": ""}])        # no id -> not done
        assert r["recorded"][0]["status"] == "Failed"
        run(tmp, "settings", "--email-mode", "approve_each")
        assert "approval" in g("g4.json", [{"oid": "o3", "action": "send", "ok": True, "id": "m3"}], ok=False)["refused"][0]["why"]
        g("g5.json", [{"oid": "o3", "action": "send", "ok": True, "id": "m3", "approved_by_user": True}])
        assert "already sent" in g("g6.json", [{"oid": "o3", "action": "send", "ok": True, "id": "m4", "approved_by_user": True}], ok=False)["refused"][0]["why"]
        run(tmp, "settings", "--email-mode", "auto")
        assert {i["oid"]: i["allowed"] for i in run(tmp, "outbox")["items"]}["o2"] == "send"
        res_, (leads, _), (log, _) = export(tmp)
        assert log[0]["Gmail Drafts"] == 1 and log[0]["Gmail Sent"] == 1 and log[0]["Gmail Failed"] == 1
        by = {l["Company"]: l for l in leads}
        assert by["Firm1"]["Outreach Status"] == "Draft created" and by["Firm3"]["Outreach Status"] == "Sent"
        import openpyxl
        apps = list(openpyxl.load_workbook(res_["file"])["Applications"].iter_rows(values_only=True))
        hdr = apps[0]
        assert any(dict(zip(hdr, r))["Gmail Status"].startswith("Draft created (id r-111)") for r in apps[1:])


@test
def b2b_never_auto_sends_and_needs_opt_out():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = with_contacts(tmp, mode="clients")
        run(tmp, "settings", "--email-mode", "auto")
        r = run(tmp, "outreach", "--updates", write(tmp, "o.json", [
            {"id": a, "to": "careers@firm1.com", "subject": "Flutter help for Firm1", "body": body("Firm1", "We build Flutter apps.")}]), ok=False)
        assert "opt-out" in r["refused"][0]["why"]
        run(tmp, "outreach", "--updates", write(tmp, "o2.json", [
            {"id": a, "to": "careers@firm1.com", "subject": "Flutter help for Firm1",
             "body": body("Firm1", "We build Flutter apps. If this isn't relevant, just say so and I won't follow up.")}]))
        assert run(tmp, "outbox")["items"][0]["allowed"] == "send_after_approval"


@test
def contacts_only_mode_blocks_outreach():
    with tempfile.TemporaryDirectory() as tmp:
        a, _, _ = with_contacts(tmp)
        run(tmp, "settings", "--email-mode", "contacts_only")
        assert "error" in run(tmp, "outreach", "--updates", write(tmp, "o.json", [{"id": a}]), ok=False)


# ------------------------------------------------------------------ repeated runs

@test
def rerun_blocks_repeat_outreach_and_rechecks_old_jobs():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = with_contacts(tmp)
        run(tmp, "settings", "--email-mode", "drafts")
        run(tmp, "outreach", "--updates", write(tmp, "o.json", [
            {"id": a, "to": "careers@firm1.com", "subject": "Flutter role at Firm1", "body": body("Firm1", "Clinic apps.")}]))
        run(tmp, "gmail", "--updates", write(tmp, "g.json", [{"oid": "o1", "action": "draft", "ok": True, "id": "r-1"}]))
        run(tmp, "track", "--updates", write(tmp, "t.json", [{"id": b, "status": "applied", "next_step": "Wait"}]))
        first = Path(tmp) / "first.xlsx"
        run(tmp, "export", "--out", str(first))
        tmp2 = Path(tmp) / "two"
        tmp2.mkdir()
        run(tmp2, *JOBS, "--posted-within", "7d", "--target", "3", "--existing", str(first), "--recheck-previous")
        st = json.loads((tmp2 / "state.json").read_text())
        assert "careers@firm1.com" in st["prior_outreach"] and len(st["rechecks"]) == 2   # applied job not rechecked
        nxt = run(tmp2, "next")
        assert nxt["action"] == "verify" and nxt["tasks"][0]["type"] == "recheck"
        run(tmp2, "apply", "--updates", write(tmp2, "rc.json", [{"id": "r1", "open": False}, {"id": "r2", "open": True}]))
        _, (leads, _), _ = export(tmp2, "second.xlsx")
        old = {l["Company"]: l for l in leads[:3]}
        assert old["Firm1"]["Verification"].startswith("Closed since last run")
        assert old["Firm2"]["Application Status"] == "Applied"                       # status preserved


# ------------------------------------------------------------------ parallel packets

@test
def shards_share_window_and_ingest_packets():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, "init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Germany, United Kingdom, Remote",
            "--offer", "Flutter dev", "--ranking", "keyword", "--verify-open", "no", "--posted-within", "7d", "--target", "4")
        sh = run(tmp, "shards", "--workers", "3", "--per-worker", "2")
        assert len(sh["packets"]) == 3 and len({json.dumps(p["window"]) for p in sh["packets"]}) == 1
        qids = [q["query_id"] for p in sh["packets"] for q in p["queries"]]
        assert len(qids) == len(set(qids)) == 6
        pkt = {qids[0]: [res(1, "Posted 1 day ago. Berlin, Germany. Flutter Dart.")],
               qids[1]: [res(2, "Posted 2 days ago. London, United Kingdom. Flutter Dart."),
                         res(3, "Posted 30 days ago. London. Flutter Dart.")]}
        r = run(tmp, "ingest", "--results", write(tmp, "p.json", pkt))
        assert r["searches"] == 2 and r["stats"]["outside_window"] == 1
        st = json.loads((Path(tmp) / "state.json").read_text())
        assert st["searches"] == 2 and len(st["issued"]) == 4


# ------------------------------------------------------------------ chat-flow fixes (live test, Nov 17)

@test
def ingest_and_apply_print_the_next_action():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *JOBS, "--posted-within", "7d", "--target", "2")
        run(tmp, "next")
        r = run(tmp, "ingest", "--results", write(tmp, "r.json", [res(1, "Posted 2d ago. Remote Flutter Dart Firebase.")]))
        assert r["next_action"]["action"] in ("search", "review", "verify", "done") and "next" not in r


@test
def boards_follow_the_options_like_the_n8n_agent():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, "init", "--mode", "jobs", "--roles", "AI Engineer", "--locations", "Lahore, Remote",
            "--posted-within", "3d", "--ranking", "keyword", "--target", "10")
        qs = []
        for _ in range(9):
            qs.append(run(tmp, "next")["query"])
            run(tmp, "ingest", "--results", write(tmp, "e.json", []))
        st = json.loads((Path(tmp) / "state.json").read_text())
        names = [b["name"] for b in st["boards"]]
        assert names[:2] == ["open_web", "linkedin"] and {"rozee", "hiredpk", "greenhouse", "remotive"} <= set(names), names
        assert qs[0] == "AI Engineer jobs Lahore posted 2 days ago", qs[0]
        assert any(q.startswith("site:linkedin.com") for q in qs) and any(q.startswith("site:rozee.pk") for q in qs), qs
        assert all("remote-first" not in q for q in qs)
        rozee = next(b for b in st["boards"] if b["name"] == "rozee")
        assert rozee["locs"] == ["Lahore"]                    # regional boards only serve their own country
    with tempfile.TemporaryDirectory() as tmp:               # user picked boards: only those (+ open web)
        run(tmp, "init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Remote", "--posted-within", "7d",
            "--ranking", "keyword", "--platforms", "Company career pages, Wellfound", "--platforms-only")
        st = json.loads((Path(tmp) / "state.json").read_text()) if (Path(tmp) / "state.json").exists() else None
        q = run(tmp, "next")["query"]
        st = json.loads((Path(tmp) / "state.json").read_text())
        assert [b["name"] for b in st["boards"]] == ["greenhouse", "lever", "workable", "ashby", "wellfound"]
        assert q.startswith("site:greenhouse.io"), q


@test
def dry_boards_are_skipped_and_productive_ones_kept():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, "init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Remote",
            "--posted-within", "7d", "--ranking", "keyword", "--verify-open", "no", "--target", "6",
            "--offer", "Flutter Dart Firebase")
        used = []
        for n in range(10):
            nx = run(tmp, "next")
            if nx["action"] != "search":
                break
            used.append(nx["board"])
            res = [res_(n, k) for k in range(2)] if nx["board"] == "remotive" else []
            run(tmp, "ingest", "--results", write(tmp, "r.json", res))
        st = json.loads((Path(tmp) / "state.json").read_text())
        dry = [b["name"] for b in st["boards"] if J.board_dry(st, b)]
        assert "linkedin" in dry and "remotive" not in dry, (dry, used)


def res_(n, k):
    return {"title": f"Flutter Developer at Rco{n}{k}", "url": f"https://remotive.com/remote/jobs/dev/flutter-{n}{k}",
            "snippet": "Posted 1d ago. Worldwide. Flutter Dart Firebase."}


@test
def profile_check_lets_writing_start_without_form_fields():
    with tempfile.TemporaryDirectory() as tmp:
        f = write(tmp, "p.json", {"full_name": "Sam", "experience": [{"title": "Dev"}], "skills": ["Flutter"]})
        r = run(tmp, "profile-check", "--profile", f, ok=False)
        assert r["ready_for_writing"] and not r["ready_for_forms"] and "phone" in r["missing_for_forms"]
        f = write(tmp, "p2.json", {"skills": ["Flutter"]})
        r = run(tmp, "profile-check", "--profile", f, ok=False)
        assert not r["ready_for_writing"] and "full_name" in r["missing_for_writing"]


@test
def page_names_hidden_employer_and_boards_are_labelled():
    results = [{"title": "AI Engineer @Remote World", "url": "https://remotive.com/remote/jobs/ai/ai-engineer-123",
                "snippet": "Posted 2d ago. Worldwide. Flutter Dart Firebase AI Engineer."}]
    with tempfile.TemporaryDirectory() as tmp:
        args = [a for a in JOBS if a not in ("--verify-open", "no")]
        args[args.index("keyword")] = "ai"
        run(tmp, *args, "--posted-within", "7d", "--target", "1")
        drive(tmp, results_fn=fixed(results),
              page_fn=lambda t: {"open": True, "posted": "Posted 2d ago", "company": "Remote World Ltd"},
              verdict_fn=lambda c: {"is_job_posting": True, "is_open": True, "is_agency": False, "fit_score": 4,
                                    "company": "Remote World (client not named)", "role": "AI Engineer",
                                    "location": "Remote", "fit_reason": "fits", "angle": "x"})
        lead = run(tmp, "plan")["leads"][0]
        assert lead["company"] == "Remote World Ltd", lead
        assert lead["apply_via"].startswith("Via Remotive"), lead["apply_via"]


@test
def no_hr_email_means_search_the_company_website_first():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = saved_run(tmp)
        r = run(tmp, "contacts", "--updates", write(tmp, "c.json", [
            {"id": a, "emails": []},
            {"id": b, "emails": [{"email": "info@firm2.com", "source_url": "https://firm2.com/contact", "evidence": "info@firm2.com"}],
             "website": "https://firm2.com"},
            {"id": c, "emails": [{"email": "careers@firm3.com", "source_url": "https://firm3.com/careers", "evidence": "careers@firm3.com"}]}]))
        inc = {x["id"]: x for x in r["incomplete"]}
        assert set(inc) == {a}, inc                       # b searched its website, c has a hiring inbox
        assert any("official website" in q for q in inc[a]["queries"])
        plan = {l["id"]: l for l in run(tmp, "plan")["leads"]}
        assert not plan[a]["contacts_checked"] and plan[a]["contact_queries"]
        assert plan[b]["contacts_checked"] and plan[c]["contacts_checked"]
        r = run(tmp, "contacts", "--updates", write(tmp, "c2.json", [
            {"id": a, "website": "https://firm1.com", "emails": [
                {"email": "hr@firm1.com", "source_url": "https://firm1.com/contact", "evidence": "HR: hr@firm1.com"}]}]))
        assert not r["incomplete"]
        assert {l["id"]: l for l in run(tmp, "plan")["leads"]}[a]["emails"] == ["hr@firm1.com"]


@test
def linkedin_gets_priority_but_not_a_monopoly():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, "init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Remote",
            "--posted-within", "7d", "--ranking", "keyword", "--target", "10")
        qs = []
        for _ in range(6):
            qs.append(run(tmp, "next")["query"])
            run(tmp, "ingest", "--results", write(tmp, "e.json", []))
        li = [q for q in qs if q.startswith("site:linkedin.com")]
        assert 1 <= len(li) <= 3, qs                      # LinkedIn is weighted, never the only source
        st = json.loads((Path(tmp) / "state.json").read_text())
        assert J.source_cap(st, "LinkedIn") == 4 and J.source_cap(st, "Remotive") == 4 - 0   # 40% vs 33% of 10
        st["config"]["target"] = 20
        assert J.source_cap(st, "LinkedIn") == 8 and J.source_cap(st, "Built In") == 7


@test
def dated_boards_are_searched_with_this_months_date_words():
    # Rozee & co print "Posting Date: Nov 09, 2026"; anchoring on the month returns fresh, dated listings.
    cfg = {"window": {"start": "2026-10-28", "end": "2026-11-03"}}
    assert J.date_hints(cfg) == ['"Nov" "2026"', '"Oct" "2026"']
    assert J.date_hints({"window": {"start": "2026-11-10", "end": "2026-11-17"}}) == ['"Nov" "2026"']
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, "init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Lahore",
            "--posted-within", "7d", "--ranking", "keyword", "--target", "10")
        qs = []
        for _ in range(6):
            qs.append(run(tmp, "next")["query"])
            run(tmp, "ingest", "--results", write(tmp, "e.json", []))
        mon = f'"{T0.strftime("%b")}" "{T0.year}"'
        rozee = [q for q in qs if q.startswith("site:rozee.pk")]
        assert rozee and mon in rozee[0], qs
        assert not any(mon in q for q in qs if q.startswith("site:greenhouse.io")), qs   # ATS pages carry no dates


@test
def role_variants_are_recognised_but_lookalikes_are_not():
    pats = J.role_matchers(["AI Engineer", "Flutter Developer"])
    hit = lambda t: any(p.search(t.lower()) for p in pats)  # noqa: E731
    for t in ["AI/ML Engineer - bilytica", "AI & ML Engineer", "Artificial Intelligence Engineer", "Senior AI Engineer",
              "Gen AI Engineer", "AI Solutions Engineer", "Flutter Dev (Remote)"]:
        assert hit(t), t
    for t in ["Air conditioning engineer", "Mail engineer", "Senior Engineer", "Sales Manager"]:
        assert not hit(t), t


@test
def a_page_of_old_listings_does_not_end_the_run():
    # n8n runs its whole search budget; one search full of expired pages must not trip the stop rule.
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, "init", "--mode", "jobs", "--roles", "Flutter Developer", "--locations", "Remote",
            "--posted-within", "7d", "--ranking", "keyword", "--target", "10")
        for n in range(3):
            assert run(tmp, "next")["action"] == "search"
            old = [res(100 * n + k, "This job has expired. Flutter Dart.") for k in range(20)]
            run(tmp, "ingest", "--results", write(tmp, "o.json", old))
        sp = Path(tmp) / "state.json"
        st = json.loads(sp.read_text())
        assert st["dry_searches"] == 3
        st["consecutive_misses"] = 200          # many rejected results (old/closed pages) ...
        sp.write_text(json.dumps(st))
        assert run(tmp, "next")["action"] == "search"     # ... still not a reason to stop
        st = json.loads(sp.read_text())
        st["dry_searches"] = 40                  # many searches in a row with nothing saved: stop
        sp.write_text(json.dumps(st))
        assert run(tmp, "next")["status"] == "retry_limit_reached"


if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            import traceback
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
            traceback.print_exc(limit=2)
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
