# Jword guide (skill details)

Install steps are in the **[main README](../README.md)** (Claude chat first, then Claude Code). This page explains what each stage does, what you control, and what you get.

## The questions Jword asks
1. **Mode:** find jobs for me, or find clients (companies hiring).
2. **Roles** and **locations** (cities, countries, Remote, Anywhere).
3. **How recently should the jobs have been posted?** Last 24 hours · 3 days · 7 days · 14 days · 30 days · 60 days · a custom range. Free text works too: *"last 10 days"*, *"between Nov 1 and Nov 10"*, *"this week"*.
4. **Your CV** (or a short summary) for jobs mode, or **what you sell** for clients mode.
5. **Platforms:** any, company career pages / ATS, LinkedIn, Indeed, Wellfound, Built In.
6. **Contacts?** Jobs only / + contact research / + contact research and personalized Gmail outreach.
7. After the job list: **how to handle emails** (contacts only / in chat / Gmail drafts / approve each send / capped auto-send), and, if a browser is available, **how to handle forms**.

## The posting window (strict)
- A job is kept only if its **original posting date** is shown and falls inside the window. The date can come from the job page (preferred; Jword opens every shortlisted job) or the search result.
- "Updated", "Reposted" and "Reviewed" dates are **not** posting dates. They can only prove a job is too old.
- Fuzzy dates are judged cautiously: with a 14-day window, "2 weeks ago" (14–20 days) is **not** accepted.
- Jobs with **no verifiable date are excluded** by default. If you explicitly allow them, they go to a separate **Undated Jobs** sheet.
- The window is **never widened** to reach the number you asked for. If only 6 jobs qualify, you get 6, and the **Excluded** sheet lists every dropped result and why.

## Contacts
- **Named:** recruiters, technical recruiters, HR, talent acquisition, hiring and recruitment managers, founders or CTOs who hire.
- **Generic:** careers@, jobs@, hr@, recruitment@, hiring@, talent@, people@, info@, contact@.
- Only addresses **published on a public page**, saved with that page and the quoted text. Guessed or pattern-built addresses are refused.
- **Verification:** *in the job post*, *company website*, or *company ATS page* = verified (can be emailed). *Third-party page* = unverified (listed, never emailed). Named people without a public email are listed as *No public email*.

## Emails (Gmail connector)
- **One email per contact**, each with its own subject and body, written for that company, job and person from your real CV. Near-copies across companies, unfilled placeholders and repeat contacts are refused by the engine.
- **Modes:** *contacts only*, *prepare in chat*, *Gmail drafts* (recommended), *ask before each send*, or *capped auto-send* (job applications to verified hiring addresses only, max 10 per run).
- **B2B (clients mode)** emails are never auto-sent, and always include an opt-out line.
- Every draft or send is recorded with the **id Gmail returned**. No id means it's recorded as failed, never as sent.
- **Re-runs** never re-email an address that was already drafted or emailed in an earlier tracker.
- Your CV can be attached through the Gmail connector. If attaching isn't possible, Jword creates a draft for you to attach it and send.

## Forms (optional)
Fills Greenhouse, Lever, Ashby, Workable, Recruitee and similar forms in Claude in Chrome or the desktop app's browser, following your submit mode. Logins, CAPTCHAs, tests, payments, unanswered questions and CV uploads it can't do are handed back to you as **Needs you**, with the exact next step. LinkedIn, Indeed, Glassdoor and ZipRecruiter applications are never automated.

## The Excel tracker
| Sheet | What's in it |
|---|---|
| **Leads** | Company, job, location, employment type, **posted date**, **posting window**, **date source**, source, job URL, **verification**, fit score, why it fits (with gaps), relevant skills, pitch, contact, email, contact source, apply via, **application / outreach / Gmail status**, next step |
| **Contacts** | Company, name, role, email, named/generic, **source URL**, **verification**, **associated job(s)**, outreach status |
| **Applications** | Application status, cover letter, answers, **outreach to / subject / body**, **Gmail status (with id)**, next action |
| **Run Log** | Window, roles, locations, platforms, agents used, totals, rejection reasons, duplicates, contacts verified vs unverified, Gmail drafts/sent/failed, limitations |
| **Excluded** | Every dropped result with its reason (outside the window, no date, closed, duplicate, wrong location…) |
| **Undated Jobs** | Only when you allowed undated listings |

**Statuses:** application: To apply · Prepared · Applied · Needs you · Skipped · Failed. Outreach: Prepared · Draft created · Sent · Failed.

**Run it again:** attach the last tracker and say *"run Jword again"*. Known jobs are skipped, old jobs are re-checked (closed ones are marked *Closed since last run*), statuses are kept, and nobody is emailed twice.

## Honest limits
- Web search only finds what it indexes. LinkedIn and Indeed jobs appear only sometimes, and many boards don't show dates (those jobs are excluded under the strict rule).
- Many companies publish **no** email, only a form. Jword reports that rather than guessing.
- Each run uses your Claude plan's usage. Contacts and emails are the heaviest stages, so start with 5–10 jobs.
- You're responsible for what's sent in your name and for commercial-email rules (CAN-SPAM, GDPR/PECR).

## For developers
Engine commands (`scripts/jword.py`): `init` · `next` · `ingest` · `apply` · `plan` · `settings` · `contacts` · `outreach` · `outbox` · `gmail` · `track` · `profile-check` · `shards` · `log` · `status` · `report` · `export`. Claude follows `SKILL.md` and the guides in `references/` (`scoring-rubric`, `sources`, `contacts`, `applicant-profile`, `applying`, `outreach`, `orchestration`). Edit only `skill/jword/`, then run `python3 tools/build_skill.py`.
