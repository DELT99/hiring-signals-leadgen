#!/usr/bin/env python3
"""Offline tests for jword.py. Drives whole runs the way Claude does, with fake web-search results.
Run:  python3 tests/test_jword.py
"""
import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import jword  # noqa: E402

COMPANIES = ["Northwind", "Contoso", "Globex", "Initech", "Umbrella", "Hooli", "Vandelay", "Stark Labs",
             "Wayne Tech", "Acme Apps", "Pied Piper", "Soylent", "Tyrell", "Cyberdyne", "Massive Dynamic"]
SOURCES = [  # (url template, title template) - five different websites
    ("https://job-boards.greenhouse.io/{slug}/jobs/{n}", "Job Application for {role} at {co}"),
    ("https://builtin.com/job/{slug}-flutter/{n}", "{role} at {co}"),
    ("https://{slug}.recruitee.com/o/{role_slug}-{n}", "{role} - {co}"),
    ("https://jobs.lever.co/{slug}/{n:08x}-aaaa-bbbb", "{co} - {role}"),
    ("https://careers.{slug}.com/jobs/{n}", "{role} | {co} Careers"),
]


def run(tmp, *argv, ok=True):
    buf, code = io.StringIO(), 0
    with contextlib.redirect_stdout(buf):
        try:
            jword.main(["--state", str(Path(tmp) / "state.json"), *argv])
        except SystemExit as e:
            code = e.code or 0
    data = json.loads(buf.getvalue())
    if ok:
        assert code == 0 and "error" not in data, data
    return data


def fake_results(n, role="Flutter Developer", city="London", sources=SOURCES):
    """Ten mixed web results: 1 listing page + postings from several sites, incl. closed/stale/agency/elsewhere."""
    res = [{"title": f"{role} Jobs in {city}", "url": f"https://www.itjobswatch.co.uk/find/{role.replace(' ', '-')}-jobs-in-{city}", "snippet": "9 of 9 jobs"}]
    for i in range(1, 10):
        k = n * 10 + i
        co = f"{COMPANIES[k % len(COMPANIES)]} {k}"
        slug = co.lower().replace(" ", "")
        url_t, title_t = sources[k % len(sources)]
        snippet = f"Posted 2 days ago · {city}, United Kingdom · Build cross-platform apps with Flutter and Dart."
        if i == 4:
            snippet = f"{city} · Flutter role. Closes 01 Jan 2025"
        if i == 5:
            snippet = f"Posted 1 day ago · {city} · Our client, a fintech, is hiring a Flutter developer. Acme Recruitment is acting as an employment agency."
        if i == 6:
            snippet = "Posted 3 days ago · Manchester, United Kingdom · Flutter and Dart apps."
        if i == 7:
            snippet = f"{city} · Oh no! This role has already been filled."
        if i == 8:
            snippet = f"Posted 3 weeks ago · {city} · Flutter."
        res.append({"title": title_t.format(role=role, co=co), "snippet": snippet,
                    "url": url_t.format(slug=slug, n=700000 + k, role_slug=role.lower().replace(" ", "-"))})
    return res


def default_verdict(c):
    t = c["title"] + " " + c["snippet"]
    loc = "Manchester, UK" if "Manchester" in t else "London, UK"
    p = jword.parse_title(c["title"], c["url"])
    return {"is_job_posting": True, "is_open": True, "is_agency": "our client" in t.lower(),
            "company": p["company"], "role": "Flutter Developer", "location": loc, "fit_score": 4,
            "fit_reason": "Hiring Flutter devs.", "angle": "Offer a Flutter squad."}


def drive(tmp, results_fn=lambda q, n: fake_results(n), verdict_fn=None, page_fn=None, max_steps=600):
    stats = {"search": 0, "review": 0, "verify": 0, "queries": []}
    for _ in range(max_steps):
        nxt = run(tmp, "next")
        act, f = nxt["action"], Path(tmp) / "io.json"
        if act == "done":
            return nxt, stats
        if act == "search":
            stats["queries"].append(nxt["query"])
            f.write_text(json.dumps(results_fn(nxt["query"], stats["search"])))
            stats["search"] += 1
            run(tmp, "ingest", "--results", str(f))
        elif act == "review":
            stats["review"] += 1
            f.write_text(json.dumps([{"id": c["id"], **(verdict_fn or default_verdict)(c)} for c in nxt["candidates"]]))
            run(tmp, "apply", "--updates", str(f))
        elif act == "verify":
            stats["verify"] += 1
            ups = []
            for t in nxt["tasks"]:
                if t["type"] == "open_check":
                    ups.append({"id": t["id"], **(page_fn or (lambda t: {"open": True, "posted": "2 days ago"}))(t)})
                else:
                    ups.append({"id": t["id"], "contact": {"name": "Sam Lee", "title": "CTO",
                                                           "url": f"https://uk.linkedin.com/in/sam-{t['company'].lower().replace(' ', '')}"}})
            f.write_text(json.dumps(ups))
            run(tmp, "apply", "--updates", str(f))
    raise AssertionError("run did not finish")


def export(tmp, name="leads.xlsx"):
    import openpyxl
    res = run(tmp, "export", "--out", str(Path(tmp) / name))
    wb = openpyxl.load_workbook(res["file"])
    def rows(sheet):
        vals = list(wb[sheet].iter_rows(values_only=True))
        return [dict(zip(vals[0], r)) for r in vals[1:]], list(vals[0])
    return res, rows("Leads"), rows("Run Log")


BASE = ["init", "--mode", "clients", "--roles", "Flutter Developer", "--locations", "London",
        "--offer", "Flutter agency building cross-platform mobile apps with Dart", "--target", "10"]
TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def unit_helpers():
    J = jword
    assert J.normalize_job_url("https://uk.linkedin.com/jobs/view/flutter-dev-at-x-4012345678?trk=a") == "https://www.linkedin.com/jobs/view/4012345678"
    assert J.normalize_job_url("https://uk.indeed.com/viewjob?jk=abc&from=serp") == "https://www.indeed.com/viewjob?jk=abc"
    assert J.normalize_job_url("https://www.Example.com/jobs/12/?utm_source=x&id=5") == "https://example.com/jobs/12?id=5"
    assert J.source_of("https://job-boards.greenhouse.io/x/jobs/1") == "Greenhouse"
    assert J.source_of("https://www.itjobswatch.co.uk/jv/x") == "IT Jobs Watch"
    assert J.source_of("https://careers.acme.co.uk/j/1") == "acme.co.uk"
    assert J.is_listing("Flutter Developer Jobs in London", "https://x.com/a")
    assert J.is_listing("54,244 Flutter Developer Jobs", "https://x.com/a")
    assert J.is_listing("Flutter Developer", "https://www.itjobswatch.co.uk/find/Flutter-jobs-in-London")
    assert J.is_listing("Flutter Jobs", "https://www.itjobswatch.co.uk/jobs/london/flutter.do")
    assert not J.is_listing("Senior Flutter Engineer", "https://builtin.com/job/senior-flutter-engineer/9139912")
    assert not J.is_listing("Mobile App Developer Job in Lahore at Acme", "https://rozee.pk/acme-jobs-1")
    assert J.parse_age("Posted 3 weeks ago")[0] == 21 and J.parse_age("yesterday")[0] == 1
    assert J.parse_age("Posted 15 Days Ago")[0] == 15 and J.parse_age("Reposted 2 Months Ago")[0] == 60
    d = (dt.date.today() - dt.timedelta(days=5)).strftime("%d.%m.%Y")
    assert J.parse_age(f"Posted: {d}")[0] == 5
    assert J.parse_age("Published Aug 20, 2025")[0] > 300
    assert J.closing_passed("Closes 01 Jan 2025") and not J.closing_passed(f"Closes 25 Nov {dt.date.today().year + 1}")
    assert J.CLOSED_RE.search("Oh no! This role has already been filled.")
    assert J.CLOSED_RE.search("Sorry, this job was removed at 12:21") and J.CLOSED_RE.search("Job no longer available")
    m = J.LocationMatcher(["Berlin", "London"])
    assert m.match("Munich, Germany")[0] == "other" and m.match("Berlin, Germany")[0] == "match"
    assert m.match("Lisbon")[0] == "unknown"
    assert J.LocationMatcher(["Germany"]).match("Munich")[0] == "match"
    assert J.LocationMatcher(["United States"]).match("Latin America")[0] != "match"
    assert J.parse_title("Senior Flutter Engineer at AJ Bell", "")["company"] == "AJ Bell"
    assert J.parse_title("Flutter Developer", "https://acme.recruitee.com/o/flutter")["company"] == "acme"
    assert J.split_list("UI/UX Designer, AI Engineer") == ["UI/UX Designer", "AI Engineer"]
    assert J.display_url("https://www.ajbell.co.uk/group/v/744?utm_source=x") == "https://www.ajbell.co.uk/group/v/744"
    assert J.normalize_job_url("https://diversityjobsgroup.com/?p=880687") == "https://diversityjobsgroup.com/?p=880687"


@test
def ai_mode_clients_full_run():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE)
        final, stats = drive(tmp)
        assert final["status"] == "target_reached", final
        res, (leads, cols), (log, _) = export(tmp)
        assert cols == jword.LEAD_COLUMNS and len(leads) == 10
        by = {}
        for l in leads:
            by[l["Source"]] = by.get(l["Source"], 0) + 1
        assert max(by.values()) <= 4 and len(by) >= 3, by                        # varied sources
        assert not any("Manchester" in str(l["Location"]) for l in leads)         # wrong location
        assert log[0]["Agency"] > 0 and log[0]["Closed"] > 0 and log[0]["Wrong Location"] > 0
        assert all(l["Contact"] == "Sam Lee (CTO)" and str(l["Contact Link"]).startswith("https://www.linkedin.com/in/") for l in leads)
        assert len({l["Job URL"] for l in leads}) == 10
        assert log[0]["Saved"] == 10 and log[0]["Ranking"] == "AI (Claude)" and log[0]["Page Checked"] >= 10
        assert all("site:" not in q for q in stats["queries"])
        print(f"   searches={stats['search']} reviews={stats['review']} verifies={stats['verify']} sources={by}")


@test
def page_check_fills_unnamed_employer():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--target", "2")
        def results(q, n):
            return [{"title": "flutter developer 146934103", "url": f"https://grabjobs.co/uk/job/flutter-developer-{n}{i}",
                     "snippet": "Flutter Developer. Company : About. Location: Paddington, London. Posted 1 day ago. Flutter and Dart."} for i in range(3)]
        def verdict(c):
            return {**default_verdict(c), "company": "", "fit_reason": "Employer not named.", "angle": "TBD"}
        flip = {"n": 0}
        def page(t):
            flip["n"] += 1
            if flip["n"] == 1:
                return {"open": None}                       # employer still unknown -> skipped in clients mode
            return {"open": True, "company": "Hyperlayer", "fit_reason": "Fintech hiring Flutter devs.", "angle": "Pitch a Flutter squad."}
        drive(tmp, results_fn=results, verdict_fn=verdict, page_fn=page)
        _, (leads, _), (log, _) = export(tmp)
        assert leads and all(l["Company"] == "Hyperlayer" and l["Why It Fits"] == "Fintech hiring Flutter devs." for l in leads), leads
        assert log[0]["Agency"] >= 1                        # the one whose employer stayed unknown
        assert all(l["Job URL"].startswith("https://grabjobs.co/") for l in leads)


@test
def one_dominant_source_still_finishes():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--ranking", "none", "--verify-open", "no", "--find-contacts", "no")
        final, stats = drive(tmp, results_fn=lambda q, n: fake_results(n, sources=SOURCES[:1]))
        assert final["status"] == "target_reached" and stats["search"] <= 6, (final, stats["search"])


@test
def page_check_rejects_closed_and_stale():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--find-contacts", "no")
        flip = {"n": 0}
        def page(t):
            flip["n"] += 1
            return [{"open": None, "page_text": "Senior Flutter Developer. This job has expired."},
                    {"open": True, "posted": "Posted 2 months ago"},
                    {"open": True, "posted": "1 day ago"}][flip["n"] % 3]
        drive(tmp, page_fn=page)
        _, (leads, _), (log, _) = export(tmp)
        assert all(l["Posted"] in ("1 day ago", "2 days ago") for l in leads), [l["Posted"] for l in leads]


@test
def keyword_mode_skips_agencies_without_review():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--ranking", "keyword", "--find-contacts", "no", "--verify-open", "no")
        final, stats = drive(tmp, verdict_fn=lambda c: (_ for _ in ()).throw(AssertionError("no review")))
        _, (leads, _), (log, _) = export(tmp)
        assert stats["review"] == 0 and final["status"] == "target_reached"
        assert all(str(l["Why It Fits"]).startswith("Keyword score") for l in leads)
        assert log[0]["Agency"] > 0


@test
def jobs_mode_keeps_agency_posts():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--mode", "jobs", "--ranking", "none", "--verify-open", "no")
        drive(tmp)
        _, (leads, _), (log, _) = export(tmp)
        assert log[0]["Agency"] == 0 and all(l["Status"] == "To apply" and l["Contact"] in (None, "") for l in leads)


@test
def low_scores_are_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--min-score", "4", "--find-contacts", "no")
        def verdict(c):
            v = default_verdict(c)
            v["fit_score"] = 5 if int(c["id"][1:]) % 2 else 2
            return v
        drive(tmp, verdict_fn=verdict)
        _, (leads, _), (log, _) = export(tmp)
        assert all(l["Fit Score"] == 5 for l in leads) and log[0]["Low Fit"] > 0


@test
def existing_file_dedup_and_append():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--target", "5")
        drive(tmp)
        first, _, _ = export(tmp, "first.xlsx")
        run(tmp, *BASE, "--target", "5", "--existing", first["file"])
        drive(tmp)
        _, (leads2, _), (log2, _) = export(tmp, "second.xlsx")
        assert len(leads2) == 10 and len(log2) == 2 and len({l["Job URL"] for l in leads2}) == 10


@test
def every_role_and_location_is_searched():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--roles", "Flutter Developer, AI Engineer", "--locations", "London, Berlin, Remote",
            "--ranking", "none", "--verify-open", "no", "--find-contacts", "no", "--location-filter", "keep-all", "--target", "25")
        _, stats = drive(tmp, results_fn=lambda q, n: fake_results(n)[:3])
        seen = {("Flutter" if "Flutter" in q else "AI", "London" if "London" in q else "Berlin" if "Berlin" in q else "Remote" if "remote" in q else "?")
                for q in stats["queries"][:6]}
        assert len(seen) == 6, seen


@test
def anywhere_has_no_location_in_query():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--locations", "Anywhere", "--ranking", "none", "--verify-open", "no", "--find-contacts", "no")
        _, stats = drive(tmp)
        assert not any("anywhere" in q.lower() or "london" in q.lower() for q in stats["queries"])


@test
def validation_errors():
    with tempfile.TemporaryDirectory() as tmp:
        assert "error" in run(tmp, "init", "--mode", "jobs", "--roles", "", "--locations", "London", ok=False)
        assert "error" in run(tmp, *BASE, "--target", "50", ok=False)
        assert "error" in run(tmp, "next", ok=False)


@test
def search_budget_stops_run():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE)
        final, stats = drive(tmp, results_fn=lambda q, n: [])
        assert final["status"] in ("max_searches_reached", "retry_limit_reached") and stats["search"] <= 40


def finished_jobs_run(tmp, target="4"):
    run(tmp, *BASE, "--mode", "jobs", "--target", target, "--ranking", "none", "--verify-open", "no")
    def results(q, n):
        r = fake_results(n)
        r[2]["snippet"] = "Posted 1 day ago · London · Flutter. To apply, send your CV to careers@globex12.com"
        r[3]["url"] = f"https://www.linkedin.com/jobs/view/40000000{n}3"
        r[3]["title"] = f"Initech {n} hiring Flutter Developer in London, England, United Kingdom | LinkedIn"
        return r
    drive(tmp, results_fn=results)
    return run(tmp, "plan")


@test
def contacts_need_a_source_and_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        plan = finished_jobs_run(tmp)
        leads = plan["leads"]
        posted = [l for l in leads if "careers@globex12.com" in l["emails"]]
        assert posted, "email printed in the posting is picked up automatically"
        lid = leads[0]["id"]
        f = Path(tmp) / "c.json"
        f.write_text(json.dumps([{"id": lid, "website": "https://acme.com", "emails": [
            {"email": "jobs@acme.com", "source_url": "https://acme.com/careers", "evidence": "Questions? Email jobs@acme.com"},
            {"email": "jane.doe@acme.com", "source_url": "https://acme.com/team", "evidence": "Jane Doe, Head of Talent", "name": "Jane Doe"},
            {"email": "guess@acme.com", "source_url": "", "evidence": "guess@acme.com"},
            {"email": "someone@gmail.com", "source_url": "https://acme.com/team", "evidence": "someone@gmail.com"},
            {"email": "Talent@Acme.com", "name": "Sara Khan", "role": "Talent Partner", "source_url": "https://acme.com/team", "evidence": "Sara Khan - Talent Partner - talent@acme.com"}]}]))
        r = run(tmp, "contacts", "--updates", str(f))
        assert {a["email"] for a in r["added"]} == {"jobs@acme.com", "talent@acme.com"}, r
        whys = " ".join(x["why"] for x in r["refused"])
        assert "evidence" in whys and "source_url" in whys and "personal mailbox" in whys
        _, (leads_x, cols), _ = export(tmp)
        assert "Email" in cols and "Apply Via" in cols and "Next Step" in cols
        import openpyxl
        wb = openpyxl.load_workbook(Path(tmp) / "leads.xlsx")
        assert wb.sheetnames == ["Leads", "Contacts", "Applications", "Run Log"], wb.sheetnames
        contacts = list(wb["Contacts"].iter_rows(values_only=True))
        assert contacts[0] == tuple(jword.CONTACT_COLUMNS) and len(contacts) >= 3
        row = next(l for l in leads_x if l["Job URL"] == leads[0]["url"])
        assert row["Email"] == "jobs@acme.com", row["Email"]           # careers-style generic beats a generic 'talent' person? both fine


@test
def tracking_statuses_and_report():
    with tempfile.TemporaryDirectory() as tmp:
        plan = finished_jobs_run(tmp)
        leads = plan["leads"]
        li = next(l for l in leads if "LinkedIn" in l["apply_via"])
        ats = [l for l in leads if "form" in l["apply_via"]]
        assert li["next_step"].startswith("Apply on LinkedIn yourself")
        f = Path(tmp) / "t.json"
        f.write_text(json.dumps([
            {"id": li["id"], "status": "applied"},                                   # refused: Claude can't submit on LinkedIn
            {"id": ats[0]["id"], "status": "applied", "message": "Dear team...", "answers": "Notice: 1 month"},
            {"id": ats[1]["id"], "status": "needs_you", "next_step": "Upload your CV and press Submit (form open in tab 3)"},
            {"id": leads[-1]["id"], "status": "bogus"}]))
        r = run(tmp, "track", "--updates", str(f), ok=False)
        assert len(r["updated"]) == 2 and len(r["errors"]) == 2, r
        f.write_text(json.dumps([{"id": li["id"], "status": "applied", "by_user": True}]))
        assert run(tmp, "track", "--updates", str(f))["ok"]
        rep = run(tmp, "report")
        assert "| # | Company |" in rep["markdown"] and "**Applied**" in rep["markdown"] and "**Needs you**" in rep["markdown"]
        assert rep["totals"]["Applied"] == 2 and rep["totals"]["Needs you"] == 1
        _, (leads_x, _), (log, _) = export(tmp)
        assert log[0]["Applied"] == 2 and log[0]["Needs You"] == 1
        import openpyxl
        apps = list(openpyxl.load_workbook(Path(tmp) / "leads.xlsx")["Applications"].iter_rows(values_only=True))
        assert apps[0] == tuple(jword.APPLICATION_COLUMNS) and len(apps) == 4
        assert any(r_["Next Step"] and "Upload your CV" in r_["Next Step"] for r_ in leads_x)


@test
def profile_check():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "p.json"
        f.write_text(json.dumps({"full_name": "Sam Lee", "email": "sam@example.com"}))
        r = run(tmp, "profile-check", "--profile", str(f), ok=False)
        assert not r["ok"] and "phone" in r["missing"] and any("cv_path" in m for m in r["missing"])
        cv = Path(tmp) / "cv.pdf"
        cv.write_bytes(b"%PDF-1.4")
        f.write_text(json.dumps({"full_name": "Sam Lee", "email": "sam@example.com", "phone": "+44 7700 900000",
                                 "location": "London, UK", "work_authorization": {"UK": "Citizen"}, "needs_sponsorship": False,
                                 "notice_period": "1 month", "salary_expectation": "Open to discuss", "cv_path": str(cv)}))
        r = run(tmp, "profile-check", "--profile", str(f))
        assert r["ok"] and r["cv_file"] == str(cv)


@test
def contacts_and_applications_append_across_runs():
    with tempfile.TemporaryDirectory() as tmp:
        plan = finished_jobs_run(tmp, target="3")
        f = Path(tmp) / "t.json"
        f.write_text(json.dumps([{"id": plan["leads"][0]["id"], "status": "prepared"}]))
        run(tmp, "track", "--updates", str(f))
        first, _, _ = export(tmp, "first.xlsx")
        run(tmp, *BASE, "--mode", "jobs", "--target", "3", "--ranking", "none", "--verify-open", "no", "--existing", first["file"])
        drive(tmp)
        export(tmp, "second.xlsx")
        import openpyxl
        wb = openpyxl.load_workbook(Path(tmp) / "second.xlsx")
        assert len(list(wb["Applications"].iter_rows())) == 2          # header + the earlier 'Prepared' row
        assert len(list(wb["Leads"].iter_rows())) == 7


@test
def preferred_platforms():
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp, *BASE, "--platforms", "Lever, Company career pages", "--platforms-only", "--ranking", "none",
            "--verify-open", "no", "--find-contacts", "no", "--target", "4")
        _, stats = drive(tmp)
        _, (leads, _), _ = export(tmp)
        assert leads and all(l["Source"] == "Lever" or l["Source"].endswith(".com") or l["Source"] in ("Recruitee", "Greenhouse") for l in leads), [l["Source"] for l in leads]
        assert not any(l["Source"] == "Built In" for l in leads)
        assert all("jobs.lever.co" in q or "careers page" in q for q in stats["queries"])
        assert "error" in run(tmp, *BASE, "--platforms", "Monster", ok=False)


if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {e!r}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
