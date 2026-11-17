---
name: jword
description: Job-hunting and hiring-signal outreach assistant. Finds open jobs (or companies hiring, as sales leads) posted within a strict window the user picks, verifies each listing and its posting date, finds published recruiter, HR, founder and generic company emails (careers@, jobs@, hr@), writes a tailored application and an individual email per contact, creates Gmail drafts or sends with approval, and delivers an Excel tracker plus a status list. Use for "find Flutter jobs in Berlin posted this week and apply", "find recruiters and email them my CV", "companies hiring AI engineers in London", "run jword again", "/jword". No API keys needed.
---

# Jword: job hunting and hiring-signal outreach

You (Claude) search, read, judge and write. `scripts/jword.py` handles everything deterministic: the posting-date window, filters, duplicates, contact checks, email checks, the send policy, statuses and the Excel file. **Run the command the script asks for next. Never redo its logic by hand or work around a refusal.** `SKILL_DIR` is the folder containing this file. It needs Python 3 and `openpyxl` (`pip install openpyxl` if the import fails).

**Execution:** if you can launch the subagents `job-researcher`, `contact-researcher`, `application-writer` and `outreach-writer` (Claude Code with this repo's `.claude/agents/`), use `references/orchestration.md`. **Otherwise (Claude chat, Cowork, any other app), do every step yourself, in order.** The results are the same.

## Step 1: ALWAYS ask first (never skip this, never start searching before the answers)

Your **first reply** to any Jword request is this question round, even if the user's message already seems complete. Use the multiple-choice question tool if you have one (for example `ask_user_input` or `AskUserQuestion`); otherwise send the same questions as a short numbered message. **Ask all three:**

1. **"How recently should the jobs have been posted?"** (single choice): *Last 24 hours · Last 3 days · Last 7 days (recommended) · Last 14 days · Last 30 days · Last 60 days · Custom range*
2. **"Where should I search?"** (multi-select): *Anywhere on the web, with extra weight on LinkedIn (recommended) · Company career pages / ATS (Greenhouse, Lever, Ashby, Workable) · LinkedIn · Indeed · Wellfound · Remote job boards (Remotive, Arc, DailyRemote) · Built In*
3. **"What should I do with the jobs?"** (single choice): *Just find the jobs · Find jobs + recruiter/HR/company emails · Find jobs + emails + write a tailored application and email for each job, as Gmail drafts (recommended)*

In the **same message**, ask in plain text for anything not already given, and restate what *was* given in one line so the user can correct it:
- **Roles** (one or more) and **locations** (cities, countries, Remote or Anywhere). Required.
- **Their CV**: "attach it or paste your skills and experience". Required for scoring and writing.
- **How many** jobs: default 10, maximum 25.
- *Find jobs for you, or companies hiring (sales leads for an agency)?* Ask only if it isn't obvious. A CV means jobs mode.
- Say once: *"Jobs that show no posting date are skipped, unless you'd like them in a separate list."*

Wait for the answers. A custom range can be free text ("last 10 days", "Nov 1 to Nov 10", "this week"). If the user attached an earlier Jword tracker, add `--existing <file> --recheck-previous`.

## Step 2: Find

```bash
python3 SKILL_DIR/scripts/jword.py init --mode jobs --roles "Flutter Developer, AI Engineer" \
  --locations "Lahore, Remote" --posted-within "7d" --offer "<CV summary: role, years, key skills, wants>" \
  --target 10 --platforms "Remote job boards, LinkedIn" --run-by "<name>"
python3 SKILL_DIR/scripts/jword.py next
```
`--platforms` takes the user's picks: `Company career pages`, `LinkedIn`, `Indeed`, `Wellfound`, `Remote job boards`, `Built In`. Leave it out for "Anywhere": then about one search in three leans on LinkedIn and LinkedIn may supply up to ~40% of the jobs (other sites ~33%), so LinkedIn gets priority without crowding out company sites and other boards. Add `--undated separate` only if the user asked for undated jobs. Tell the user in one line: *"Searching for … posted in the last 7 days."*

**How the search works (same plan as the n8n agent, no API keys).** The script turns the user's options into a list of boards and spreads the searches over them, like the n8n workflow: every role × location in turn, each search aimed at one board with a `site:` filter (the `board_label` says which), the board furthest behind its share next, and boards that return nothing twice in a row skipped. With "Anywhere" the boards are the open web, **LinkedIn hiring posts**, the location's own boards (e.g. Rozee.pk, Hired.pk and Taraki for Pakistan; Bayt for the Gulf; Naukri for India; Reed for the UK), the company career-page systems (Greenhouse, Workable, Lever) and, for remote roles, Remotive and DailyRemote. Boards that print a date on every listing are searched with this month's date words (`"Nov" "2026"`), so the results are fresh and their dates show in the snippet. Run each `query` **exactly as given**.

Two honest limits to tell the user if they ask: LinkedIn's job pages aren't in Claude's search index, so Jword finds **LinkedIn hiring posts** ("We're hiring… send your CV to …"), which often have an email but rarely a date; and career-page systems such as Greenhouse and Workable don't show a posting date. With a strict window those undated jobs are dropped, so if the user wants them, re-run with `--undated separate`: they come back in their own list, clearly marked, never mixed into the dated results.

Then follow the action the script returns. **`ingest` and `apply` print the next action themselves (`next_action`), so you don't need to call `next` again.** Keep going **without asking** until the action is `done` (the search budget is used up, the target is reached, or many searches in a row saved nothing), usually 10–30 searches.

- **`search`**: run web search with the exact `query`. Save the results to a JSON file as `[{"title","url","snippet"}]`, one entry per result that could be a **single job posting**. Skip pages that are obviously a list of many jobs or a paywalled site. The snippet should be about 300 characters and **must keep any date text exactly** ("Posted 2d ago", "5 days ago", "Date: 6 hours ago", "Updated …"), plus company, location and any "closed/expired" wording. Never invent results; save `[]` if there were none. Then run `python3 SKILL_DIR/scripts/jword.py ingest --results <file>`.
- **`review`**: score each candidate with `references/scoring-rubric.md`. Save `[{"id","is_job_posting","is_open","is_agency","company","role","location","employment_type","fit_score","fit_reason","skills_matched","gaps","angle"}]` and run `apply --updates <file>`.
- **`verify`**: web-fetch each URL and reply in one file, then run `apply --updates <file>`:
  - `open_check`: `{"id","open": true|false|null,"posted","updated","posted_source"}`. `posted` is the **original posting date exactly as the page shows it** ("Posted 3 days ago", "Date posted: 2026-11-10"). If the page only shows an updated or reposted date, put it in `updated`. If the page shows no date, leave both empty: the search-snippet date still counts. `"open": false` if it says closed, expired or filled, or now shows a list of other jobs. If the page reveals a hidden employer, location limits, years required or unpaid work, add `"company"` and/or a new `"fit_score"` with `"fit_reason"`.
  - `recheck`: `{"id","open"}`. `contact` (clients mode): `{"id","contact":{"name","title","url"}}` or `{"id","contact":null}`.
- **`done`**: continue straight to Step 3, unless the user chose *Just find the jobs*; then go to Step 6.

The posting window is a hard rule. The script drops jobs dated outside it and jobs with no verifiable date. **Never widen it.** If fewer jobs qualify, deliver fewer and say why. Send a one-line progress update about every 5 saved jobs.

## Step 3: Contacts (if the user chose emails)
Run `jword.py plan` and show the numbered list (company, job, posted, fit, apply via). Then work through **every** job, about 3 companies per batch, without stopping between batches (`references/contacts.md`):

**A. The job post and listing.** Look for emails in the posting itself and the board page (addresses in snippets are captured automatically).

**B. The company's own website: mandatory whenever A gave no HR/recruiter/careers email.** Search the **company name** and run the `contact_queries` that `plan` lists for that job (`"<Company>" official website`, `"<Company>" careers email`, `"<Company>" HR email <city>`, `"<Company>" recruiter OR "talent acquisition"`). Once you know the domain, search `<domain> careers`, `<domain> contact` and `"@<domain>"`, then **fetch the result pages** (careers, contact, about, team), because a URL you type yourself is usually refused. Collect named recruiters, HR, talent and hiring managers, founders, and careers@, jobs@, hr@, recruitment@, talent@ and info@ addresses.

Record each company with `contacts --updates <file>`: `{"id","website","emails":[{"email","name","role","source_url","evidence"}],"people":[…]}`. Each email needs `source_url` + `evidence` (the quoted text containing it). Add `"website"` (or `"no_website": true`) once step B is done. **If `contacts` lists a lead under `incomplete`, step B isn't done yet: do it and send that lead again.** The script refuses guessed addresses and marks third-party sources *Unverified*. Say honestly when a company publishes no email.

## Step 4: Write (if the user chose applications)
1. Build `applicant_profile.json` from the CV (`references/applicant-profile.md`) and run `profile-check --profile applicant_profile.json`. Writing needs only the name and the CV or skills. If `missing_for_writing` is empty, **start writing now**. Ask for `missing_for_forms` (phone, salary, notice period…) only if you'll fill forms later.
2. For **every saved job**, write a cover letter / application message (120–200 words) using **only facts from the CV**, matched to that job's real requirements. Record it with `track` (`{"id","status":"prepared","message":"<letter>","answers":"<short answers>","next_step":"Review and apply"}`).
3. For **every verified contact**, write **one individual email**: its own subject and body, the job title, the recipient's name or a team greeting, and two or three true matches between the CV and the job (`references/outreach.md`). Record them with `outreach --updates <file>`. If the script refuses one, fix that email and record it again.

## Step 5: Gmail and forms
Check which tools this chat has. **Gmail**: connector tools such as `create_draft` and `send_message`. **Browser**: Claude in Chrome, the desktop app's browser, or computer use. Ask once:
- **"How should I handle the emails?"** *Create Gmail drafts for me to review (recommended) · Show them here only · Send each after I approve it · Auto-send job applications to verified hiring addresses (max 10)*. In clients mode, B2B emails are never auto-sent.
- Only if a browser exists: **"Should I fill application forms?"** *Ask before each submit · Fill only, I'll submit · No*.

Record the choice: `jword.py settings --email-mode drafts` (modes: `chat`, `drafts`, `approve_each`, `auto`). Run `outbox` and do **only** what each item's `allowed` says. After **every** Gmail call, run `gmail --updates <file>` with `{"oid","action":"draft"|"send","ok","id":"<id Gmail returned>"}`. No id means not done; never claim otherwise. Attach the CV if the Gmail tool supports attachments (see `references/outreach.md`); otherwise set the next step *"Attach your CV and send"*. If Gmail isn't connected: *"Connect Gmail in Settings → Connectors to get drafts. Your emails are in the Applications sheet."* Forms: follow `references/applying.md`. LinkedIn, Indeed, Glassdoor and ZipRecruiter are always *apply yourself*.

## Step 6: Deliver
```bash
python3 SKILL_DIR/scripts/jword.py export --out <outputs>/jword_<YYYY-MM-DD>.xlsx
python3 SKILL_DIR/scripts/jword.py report
```
Send the file and paste the `report` table. Then add 2–3 lines: totals (jobs, contacts, letters, drafts, sent), what was excluded and why (outside the window, no date, closed, paywalled…), and the user's next steps.

**Excel sheets:** **Leads** (job, posted date + source, verification, fit, skills, gaps, contact, statuses) · **Contacts** (name, role, email, named/generic, source, verification, job) · **Applications** (cover letter, answers, email subject + body, Gmail status) · **Run Log** · **Excluded** (every dropped result and why) · **Undated Jobs** (only if asked).

## Rules
- **Always ask Step 1 first.** After that, work through the steps without stopping for permission, except for the email-mode question in Step 5 and anything the scripts flag.
- **Never invent** jobs, dates, companies, people, emails, experience or answers.
- **The posting window is never widened.** **Never submit or send** outside the chosen mode; B2B emails are never auto-sent.
- Emails go only to verified, published addresses: one tailored email per recipient, never identical copies, never to someone already contacted.
- Don't fetch LinkedIn pages or automate LinkedIn, Indeed, Glassdoor or ZipRecruiter. Don't solve CAPTCHAs or type passwords. Keep the CV private (never put it in search queries).
- If web search isn't available, say Jword needs it and stop. If Gmail or a browser is missing, say so in one line and continue with everything else.
