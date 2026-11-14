---
name: jword
description: Find open jobs or hiring-signal leads from public job postings, find company contact emails (careers, HR, recruiters, founders) from public pages, prepare tailored applications, fill and submit them in the browser, and email them via Gmail, delivering an Excel tracker plus a status list. Use for "find 10 Flutter jobs in Berlin and apply for me", "find companies hiring AI engineers in London" (sales leads), "get HR emails for these jobs", "jword", "run my job search". No API keys needed.
---

# Jword: hiring-signal lead engine

A job post means a company has a need right now. Jword works in stages, and the user chooses which ones to run:

1. **Find** open jobs (jobs mode) or companies that are hiring (clients mode): searched, filtered, scored and page-checked.
2. **Contacts** *(optional)*: emails published by those companies (careers@, HR, recruiters, founders) from their own public pages.
3. **Prepare** *(optional, jobs mode)*: a tailored cover letter and answers for each job, built only from the user's CV or profile.
4. **Apply** *(optional)*: fill and submit application forms in the browser, and/or send applications or outreach by Gmail.
5. **Deliver**: an Excel tracker and a status list in chat.

You (Claude) search, read, judge, write and drive the browser. `scripts/jword.py` does the exact bookkeeping: search plan, filters, scoring rules, de-duplication, contact validation, status tracking and the Excel file. **Always do what the script says next. Never rebuild its logic by hand.** `SKILL_DIR` is the folder containing this file.

## Step 1: Gather the inputs

Read what the user already said; ask only for what's missing. Use the multiple-choice question tool if you have one, otherwise one short message.

| Input | Ask? | Default / notes |
|---|---|---|
| Mode | **Always** | *Find jobs for me* or *Find clients* (companies hiring) |
| Roles | **Always** | One or more, e.g. `Flutter Developer, AI Engineer` |
| Locations | **Always** | Any cities or countries, `Remote`, or `Anywhere` |
| CV / offer | **Always** | Jobs: **the user's CV (attach it) or a summary of skills and experience**, which is required for scoring and applying. Clients: what they sell |
| Platforms | **Always** (multi-select) | *Any (recommended for finding)*, *Company career pages / ATS: Greenhouse, Lever, Ashby, Workable (best for auto-apply)*, *LinkedIn*, *Indeed*, *Wellfound*, *Built In*. Pass as `--platforms`; add `--platforms-only` if the user wants nothing else |
| Number | If not given | **10** (or 25; maximum 25) |
| Ranking / min score / posted within / open-check / location filter / agencies | No | `ai` / 3 / `week` / yes / `strict` / skip agencies in clients mode, keep them in jobs mode |
| Earlier Jword file | If attached | `--existing <file>`: its jobs are skipped; the new ones are appended (all four sheets) |

## Step 2: Find (the search loop)

```bash
python3 SKILL_DIR/scripts/jword.py init --mode jobs --roles "Flutter Developer, AI Engineer" \
  --locations "Berlin, Remote" --offer "<CV summary or what they sell>" --target 10 \
  --platforms "Company career pages, Lever, Greenhouse" --run-by "<name>"
```
Tell the user in one line what you're doing. Then repeat `python3 SKILL_DIR/scripts/jword.py next` until it says `done`. It returns one action:

- **`search`**: run your web search with the exact `query`. Write **every** result to JSON as `[{"title","url","snippet"}]`, keeping the title, company, location, "Posted …", "Closes …" and any "expired / filled / removed" wording (up to ~700 characters per snippet). Never invent results; use `[]` if the search failed. Then run `ingest --results <file>`.
- **`review`** (AI ranking): score each candidate with `references/scoring-rubric.md` and write `[{"id","is_job_posting","is_open","is_agency","company","role","location","fit_score","fit_reason","angle"}]`. Then run `apply --updates <file>`.
- **`verify`**:
  - `open_check`: web-fetch the URL. Reply `{"id","open": true|false|null,"posted"}`. If the listing hid the employer and the page names it, add `"company"` plus a rewritten `"fit_reason"` and `"angle"`. If unsure, add `"page_text"` (first ~3000 characters).
  - `contact` (clients mode): web-search the query. Pick a person only if a result clearly shows their **name and title at this company**: `{"id","contact":{"name","title","url"}}` or `{"id","contact":null}`.
  - Apply all replies with `apply --updates <file>`.
- **`done`**: go to Step 3.

Give the user a one-line update about every 5 saved jobs; don't narrate every step.

## Step 3: Ask what to do next

Run `python3 SKILL_DIR/scripts/jword.py plan` and show a short numbered list (company, job, fit score, how to apply). **Check what's available in this chat first**, and only offer what can actually be done:
- **Browser**: Claude in Chrome tools, the built-in browser, or computer use. If none is available: "Filling forms needs Claude in Chrome or the Claude desktop app's browser".
- **Gmail**: Gmail connector tools such as create_draft or send_message. If missing: "Connect Gmail under Settings → Connectors to email applications".

Then ask (multi-select). Every option can be skipped:

**"What should I do with these jobs?"**
- Find contact emails (careers, HR, recruiters, founders)
- Prepare tailored applications (cover letter + answers): *jobs mode*
- Fill and submit applications in the browser: *jobs mode, needs a browser*
- Email applications / outreach via Gmail: *needs Gmail*
- Nothing else, just give me the Excel

If they chose **submitting**, ask **"How should I submit?"**: *Ask me before each submit (recommended)* / *Submit automatically when every answer comes from my profile; ask only if something's missing* / *Fill the forms, I'll press Submit myself*.
If they chose **email**, ask **"How should I send?"**: *Gmail drafts for me to review (recommended)* / *Send each after I approve it* / *Auto-send job applications to published careers/HR addresses (max 10 per run)*. Cold outreach in **clients mode** is always drafts or approve-each, never auto-sent.
Also say: *"Reply with job numbers to skip any."* Then mark the skipped ones with `track` status `skipped`.

## Step 4: Contacts *(if chosen)*
Follow **`references/contacts.md`**. For each job, use only emails that appear on public pages (the job post, the company's careers/contact/about/team pages, press pages, or search results showing the address). Record them with `contacts --updates <file>`; each email needs its `source_url` and `evidence` (the quoted text containing the address). **The script refuses guesses.** Emails printed in the posting are captured automatically.

## Step 5: Prepare *(if chosen, jobs mode; required before submitting)*
1. Build the **applicant profile** from the CV or details: `references/applicant-profile.md`. Save it as `applicant_profile.json` and run `profile-check --profile applicant_profile.json`. Ask the user for every missing field in **one** message (yes/no items as options). Never fill gaps yourself.
2. For each job, write a cover letter (≤200 words) and short answers to common questions **using only facts from the profile**. Record each with `track` status `prepared`, putting the letter in `message` and a one-line summary in `answers`.

## Step 6: Apply *(if chosen)*
- **Browser** (`references/applying.md`): load the browser's own skill first if one is listed (e.g. `chrome-browser` / `built-in-browser`). Fill one form at a time and follow the chosen submit mode exactly. **Hand back to the user** (status `needs_you` + a precise `next_step`) when there's a login or account creation, a CAPTCHA, an assessment or video interview, payment, a question the profile doesn't answer, or a **CV upload you can't perform**: leave the form open and say so, e.g. *"Upload your CV and press Submit: tab 3, Acme form"*. **LinkedIn, Indeed, Glassdoor and ZipRecruiter** (`apply_via` says *apply yourself*): never submit there; give the user the link and the prepared answers.
- **Gmail** (`references/outreach.md`): one email per company, to the best address. Attach the CV if the Gmail tool supports attachments; otherwise create a draft and set `next_step` to *"Attach your CV and send"*.
- After **every** action, record it straight away: `track --updates <file>` with `{"id","status","next_step","message","answers"}`. Statuses: `applied`, `prepared`, `needs_you`, `draft_ready`, `emailed`, `skipped`, `failed`. If the **user** applied on a no-automation site, add `"by_user": true`.

## Step 7: Deliver
```bash
python3 SKILL_DIR/scripts/jword.py export --out <outputs>/jword_<YYYY-MM-DD>.xlsx
python3 SKILL_DIR/scripts/jword.py report
```
Give the user the file and **paste the `report` markdown table** (company, job, fit, apply via, email, **status**, **next step**). Then add 2–3 lines: totals (applied / needs you / emailed / skipped), what was filtered and why, and what the user should do next, starting with the *Needs you* items.

**Sheets:** **Leads** (Date Added, Mode, Company, Job Title, Location, Posted, Source, Job URL, Fit Score, Why It Fits, Pitch / Tip, Contact, Contact Link, Email, Apply Via, Status, Next Step, Run ID) · **Contacts** (Company, Name, Role, Email, Type, Found On, Run ID) · **Applications** (Date, Company, Job Title, Job URL, Apply Via, Status, Next Step, Cover Letter / Message, Answers Used, Run ID) · **Run Log**.

## Rules
- **Never invent** jobs, companies, people, email addresses, experience, qualifications, dates or answers. If it isn't in the profile, ask or hand back to the user.
- **Never submit or send** except in the mode the user chose. If in doubt, stop and ask. Applications and emails can't be taken back.
- Don't fetch LinkedIn pages, and don't automate LinkedIn, Indeed, Glassdoor or ZipRecruiter applications.
- Don't solve CAPTCHAs, create accounts, or enter passwords. The user does those.
- Emails: published business addresses only, with the source recorded. No guessing (`first.last@`), no personal mailboxes unless the job post lists one, no scraping behind logins. In clients mode, keep outreach honest and short, with an easy opt-out line.
- Keep the CV and profile private: use them only to fill the user's own applications, and never put them in search queries.
- If web search isn't available, tell the user Jword needs it and stop.
