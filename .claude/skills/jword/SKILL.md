---
name: jword
description: Job-hunting and hiring-signal outreach assistant. Finds open jobs (or companies hiring, as sales leads) posted within a strict window the user picks, verifies each listing and its posting date, finds published recruiter, HR, founder and generic company emails (careers@, jobs@, hr@), writes tailored applications and an individual email per contact, creates Gmail drafts or sends with approval, and delivers an Excel tracker plus a status list. Use for "find Flutter jobs in Berlin posted this week and apply", "find recruiters and email them my CV", "companies hiring AI engineers in London", "run jword again", "/jword". No API keys needed.
---

# Jword: job hunting and hiring-signal outreach

A job post means a company has a need right now. Jword runs in stages, and the user chooses which ones:

1. **Find** open jobs (*jobs* mode) or companies hiring (*clients* mode), posted inside the user's window.
2. **Contacts**: published emails of recruiters, HR, hiring managers, founders, plus generic hiring inboxes.
3. **Prepare**: a cover letter and answers per job, using only facts from the CV.
4. **Outreach and apply**: one individual email per contact (Gmail drafts or approved sends), and form filling in a browser.
5. **Deliver**: an Excel tracker plus a status table in chat.

You (Claude) search, read, judge, write and act. `scripts/jword.py` is the source of truth for every deterministic part: the posting-date window, filters, de-duplication, contact validation, email checks, the send policy, status tracking and the Excel file. **Do what the script says next. Never redo its logic by hand or override a refusal.** `SKILL_DIR` is the folder containing this file. Python 3 with `openpyxl` is required (install with `pip install openpyxl` if it's missing).

**How to execute:** if you can launch the subagents `job-researcher`, `contact-researcher`, `application-writer` and `outreach-writer` (Claude Code with this repo's `.claude/agents/`), follow `references/orchestration.md` for parallel work. Otherwise (Claude chat, Cowork, or any other app), do every stage yourself, in order and in small batches. The results and rules are the same either way.

## Step 1: Gather the inputs (before any search)

Read what the user already said and ask only for what's missing, in **one** round. Use the multiple-choice question tool if you have one.

| Input | Ask? | Notes |
|---|---|---|
| Mode | **Always** | *Find jobs for me* or *Find clients* (companies hiring) |
| Roles | **Always** | One or more, e.g. `Flutter Developer, AI Engineer` |
| Locations | **Always** | Cities, countries, `Remote` or `Anywhere` |
| **Posted within** | **Always** | Ask: **"How recently should the jobs have been posted?"** Options: *Last 24 hours / Last 3 days / Last 7 days / Last 14 days / Last 30 days / Last 60 days / Custom date range*. Free text works too: "last 10 days", "between Nov 1 and Nov 10", "this week". Pass it as `--posted-within`. |
| Undated jobs | Only if the user mentions them | Default: excluded. `--undated separate` lists them in their own sheet, only if the user explicitly allows it |
| CV / offer | **Always** | Jobs mode: **the CV (attach it) or a summary of skills and experience**, which is needed for scoring and writing. Clients mode: what they sell |
| Platforms | **Always** (multi-select) | *Any (recommended)*, *Company career pages / ATS*, *LinkedIn*, *Indeed*, *Wellfound*, *Built In* → `--platforms` (add `--platforms-only` if the user wants nothing else) |
| Contacts | **Always** | **"Would you like me to find company contacts and publicly available email addresses too?"** *Jobs only / Jobs + company contact research / Jobs + contact research + personalized Gmail outreach* |
| Number | If not given | **10** (maximum 25) |
| Earlier Jword file | If attached | `--existing <file> --recheck-previous`: skips known jobs, keeps statuses, re-checks old jobs, never re-emails |

**The posting window is a hard rule.** The script drops jobs dated outside it, and jobs with no verifiable *original* posting date. "Updated", "reposted" or "reviewed" dates are not posting dates. **Never widen the window to reach the number.** If fewer jobs qualify, deliver fewer and say why.

## Step 2: Find (the search loop)

```bash
python3 SKILL_DIR/scripts/jword.py init --mode jobs --roles "Flutter Developer, AI Engineer" \
  --locations "Berlin, Remote" --posted-within "7d" --offer "<CV summary or what they sell>" \
  --target 10 --platforms "Company career pages, LinkedIn" --run-by "<name>"
```
Tell the user in one line what you're doing (including the window). Then repeat `python3 SKILL_DIR/scripts/jword.py next` until it says `done`:

- **`search`**: run your web search with the exact `query`. Save **every** result to JSON as `[{"title","url","snippet"}]`, keeping the company, location, any "Posted …", "Updated …" or "Closes …" text, and any "expired / filled" wording (up to ~700 characters). Never invent results; save `[]` if the search failed. Then run `ingest --results <file>`.
- **`review`**: score each candidate with `references/scoring-rubric.md` and save `[{"id","is_job_posting","is_open","is_agency","company","role","location","employment_type","fit_score","fit_reason","skills_matched","gaps","angle"}]`. Then run `apply --updates <file>`.
- **`verify`**, then `apply --updates <file>` with all replies:
  - `open_check`: web-fetch the URL. Reply `{"id","open": true|false|null,"posted","updated","posted_source"}`. `posted` is the **original posting date exactly as the page labels it** ("Posted 3 days ago", "Date posted: 2026-11-10", JSON-LD `datePosted`). If the page only shows an updated or reposted date, put it in `updated` and leave `posted` empty. If the employer was hidden and the page names it, add `"company"` with a rewritten `"fit_reason"` and `"angle"`. If the page changes the fit (location limits, years required, unpaid), add a new `"fit_score"`. If the URL now shows a list of *other* jobs, use `"open": false`. If the fetch fails, search once for the company's own posting and check that.
  - `recheck`: a job from the earlier tracker. Reply `{"id","open"}`.
  - `contact` (clients mode): pick a person only if a result clearly shows their **name and title at this company**: `{"id","contact":{"name","title","url"}}` or `{"id","contact":null}`.
- **`done`**: go to Step 3.

Send a one-line update about every 5 saved jobs. Don't narrate each step.

## Step 3: Agree what happens next

Run `jword.py plan` and show a short numbered list (company, job, posted date, fit, how to apply). **Check which tools this chat really has** and only offer what can be done:
- **Gmail**: connector tools such as `create_draft` and `send_message`. If missing: *"Connect Gmail in Settings → Connectors to create drafts; meanwhile I can write the emails here."*
- **Browser**: Claude in Chrome, the desktop app's built-in browser, or computer use. If missing: *"Form filling needs Claude in Chrome or the Claude desktop app's browser."*

If the user chose contacts in Step 1, confirm it. Then ask:
- **"How would you like me to handle the emails?"** *Find contacts only / Prepare emails in chat / Create Gmail drafts (recommended) / Ask for approval before sending each email / Capped automatic sending (job applications to verified hiring addresses only, max 10)*. In clients mode, B2B emails are **never** sent automatically: offer drafts or approve-each only.
- Only if a browser is available: **"Should I fill application forms?"** *Ask me before each submit (recommended) / Submit when every answer is from my profile / Fill only, I'll press Submit / No forms*.
- *"Reply with job numbers to skip any."* (record those with `track` status `skipped`)

Save the choices before acting: `jword.py settings --email-mode drafts --submit-mode ask_each --contact-research contacts_outreach` (email modes: `contacts_only`, `chat`, `drafts`, `approve_each`, `auto`). Drafts permission is **not** send permission.

## Step 4: Contacts (if chosen)
Follow **`references/contacts.md`**. For every shortlisted company, find **all** useful published contacts: named recruiters, HR, talent acquisition, hiring managers and founders, plus generic hiring inboxes (careers@, jobs@, hr@, recruitment@, talent@, info@). Record them with `contacts --updates <file>`. Each email needs its `source_url` and `evidence` (the quoted text containing the address); named people with no public email go in `people`. The script refuses guesses and marks third-party sources *Unverified*. Those are never emailed. If nothing is found, say so plainly.

## Step 5: Prepare (jobs mode)
1. Build the **applicant profile** from the CV (`references/applicant-profile.md`), save it as `applicant_profile.json` and run `profile-check --profile applicant_profile.json`. Ask for all missing fields in **one** message. Never fill gaps yourself.
2. For each job, write a cover letter (≤200 words) and short answers, using **only facts from the profile** and the job's real requirements. Record them with `track` (status `prepared`, letter in `message`, a summary in `answers`).

## Step 6: Outreach and apply
- **Emails** (`references/outreach.md`): write **one individual email per verified contact**: its own subject, the real job, the recipient's name and role (or a generic-inbox greeting), and the user's true, relevant experience. Record them with `outreach --updates <file>`. The script refuses unverified recipients, placeholders, near-copies across companies and repeat contacts. Show the user the recipients and subjects, run `outbox`, and do **only** what each item's `allowed` says (`draft`, `send`, `send_after_approval` = show the email and wait for a yes, or `none` = chat only). After **every** Gmail call, record the result with `gmail --updates <file>` and the **id the connector returned**. Never say an email was sent or drafted without that id.
- **Forms** (`references/applying.md`): follow the chosen submit mode exactly. Hand back to the user (`needs_you` + a precise `next_step`) for logins, CAPTCHAs, tests, payments, unanswered questions, or a CV upload you can't do. LinkedIn, Indeed, Glassdoor and ZipRecruiter: never submit; give the link and the prepared answers.
- Record each application step at once with `track` (`applied`, `prepared`, `needs_you`, `skipped`, `failed`).

## Step 7: Deliver
```bash
python3 SKILL_DIR/scripts/jword.py export --out <outputs>/jword_<YYYY-MM-DD>.xlsx
python3 SKILL_DIR/scripts/jword.py report
```
Send the file and **paste the `report` table**. Then add 2–3 lines: totals (applied, drafts, sent, needs you), what was excluded and why (from `excluded`: outside the window, no date, closed, duplicates…), and the user's next steps, starting with *Needs you*.

**Sheets:** **Leads** (one row per job: posting date, its source, the window, verification, fit, relevant skills, contact, application, outreach and Gmail status, next step) · **Contacts** (name, role, email, named/generic, source URL, verification, associated job, outreach status) · **Applications** (cover letter, answers, outreach subject and body, Gmail status, next action) · **Run Log** (window, platforms, agents used, rejection reasons, contact and Gmail totals, limitations) · **Excluded** (every dropped result and why) · **Undated Jobs** (only with `--undated separate`).

## Rules
- **Never invent** jobs, dates, salaries, companies, people, email addresses, qualifications, experience or answers.
- **The posting window is never relaxed**, by you or by any subagent.
- **Never submit or send** outside the chosen mode. B2B sales emails are never auto-sent. When in doubt, stop and ask: applications and emails can't be taken back.
- **Emails go only to verified, published addresses**, one tailored email per recipient, never identical copies, and never to an address already contacted (this run or earlier) unless the user explicitly asks.
- Don't fetch LinkedIn pages or automate LinkedIn, Indeed, Glassdoor or ZipRecruiter. Don't solve CAPTCHAs, create accounts or type passwords.
- Keep the CV private: use it only for the user's own applications, never in search queries.
- If web search isn't available, say that Jword needs it and stop. If Gmail or a browser is missing, say so in one line and continue with everything else.
