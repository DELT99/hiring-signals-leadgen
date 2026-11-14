# Jword: the Claude skill edition

**Jword** turns Claude into a job-search and lead-gen assistant, with **no n8n, no API keys and no setup**. It finds open jobs (or companies that are hiring), finds the companies' published contact emails, prepares tailored applications, fills and submits forms in your browser, and emails applications through Gmail. **You choose each step, and every step can be skipped.**

> *"Use Jword: find 10 Flutter developer jobs in Berlin or remote and apply for me. My CV is attached."*

## What it does
| Stage | What happens | Needs |
|---|---|---|
| 1. **Find** | Searches the open web for every role × location, filters out listing pages, closed or expired jobs, wrong locations and agency posts, scores each job against your CV, and opens qualified postings to confirm they're still open | Web search |
| 2. **Contacts** *(optional)* | Finds emails the company **publishes**: careers@, HR, recruiters, founders, from the job post and the company's careers/contact/team pages. Every email is saved with the page it came from; guesses are refused | Web search |
| 3. **Prepare** *(optional)* | Builds your applicant profile from your CV, asks once for anything missing (work authorization, notice period, salary…), and writes a cover letter and answers per job, **only from your real details** | Your CV or details |
| 4. **Apply** *(optional)* | Fills application forms (Greenhouse, Lever, Ashby, Workable, Recruitee…) and/or emails applications via Gmail, in the mode you pick | A browser (Claude in Chrome or the Claude desktop app), and the Gmail connector for email |
| 5. **Deliver** | An Excel tracker, plus a **status list in chat**: applied, needs you, emailed, skipped, and what to do next | – |

**You stay in control:**
- **Submitting:** *ask me before each submit* (default), *auto-submit only when every answer comes from my profile*, or *fill the forms and I'll press Submit*.
- **Emails:** *Gmail drafts* (default), *send after I approve each*, or *auto-send job applications to published careers/HR addresses* (max 10 per run). Cold sales outreach is never auto-sent.
- **Handed back to you** (marked **Needs you**, with a precise next step): logins and account creation, CAPTCHAs, assessments, questions your profile doesn't answer, and **CV uploads Claude can't do** ("Upload your CV and press Submit: tab 3").
- **LinkedIn, Indeed, Glassdoor and ZipRecruiter** forbid automated applying, so Jword prepares your answers and gives you the link, but never submits there.

## Install or update (2 minutes)
1. Download **[`dist/jword.zip`](../dist/jword.zip)**: open it on GitHub → **Download raw file**. **Don't unzip it.**
2. In Claude, go to **Customize → Skills**. *Updating?* Click **⋯** next to the old Jword → **Delete** first.
3. Click **+** → **Create skill** → **Upload a skill**, choose `jword.zip`, and toggle it **on**.
4. For applying and emailing, also turn on:
   - **Web search** in your chat, needed for everything
   - **A browser** for filling forms: the **Claude in Chrome** extension, or the **Claude desktop app**'s built-in browser
   - **Gmail** for emailing: **Settings → Connectors → Gmail**

Skills need *Code execution and file creation* on (it's on by default on most plans; Team/Enterprise admins may need to enable it).

## Use it
- *"Find 10 AI engineer jobs in London or remote that fit my CV (attached), get the HR emails, and apply."*
- *"Find 25 Flutter jobs on company career pages in Germany. Just the list, no applying."*
- *"Find companies hiring React developers in Dubai. We're a dev agency. Find their emails and draft outreach in Gmail."* (clients mode)
- *"Run Jword again"* + attach last time's Excel: no repeats, and all sheets carry on.

## The Excel file
| Sheet | Columns |
|---|---|
| **Leads** | Date Added, Mode, Company, Job Title, Location, Posted, Source, Job URL, Fit Score, Why It Fits, Pitch / Tip, Contact, Contact Link, **Email**, **Apply Via**, **Status**, **Next Step**, Run ID |
| **Contacts** | Company, Name, Role, Email, Type (Generic/Person), **Found On** (the page it came from), Run ID |
| **Applications** | Date, Company, Job Title, Job URL, Apply Via, Status, Next Step, Cover Letter / Message, Answers Used, Run ID |
| **Run Log** | One row per run: inputs, leads per source, skip reasons, emails found, applied / emailed / needs you, status |

**Statuses:** To apply · Prepared · Applied · Needs you · Draft ready · Emailed · Skipped · Failed (clients mode starts at *New*).

## Honest limits
- **Usage:** each run uses your Claude plan's usage; applying is the heaviest part. Default is 10 jobs, maximum 25.
- **Coverage:** web search finds what it indexes; LinkedIn and Indeed jobs appear only occasionally.
- **Emails:** many companies publish **no** address and use forms instead (in testing, Waracle uses only a talent-pool form). Jword reports that rather than guessing.
- **Forms vary:** CV upload depends on the browser tool; when it can't upload, the job becomes *Needs you*.
- **You're responsible** for what's sent in your name, and for local email rules in sales outreach (CAN-SPAM, GDPR/PECR). Review drafts.
- It runs when you ask, not on a schedule.

## Development
```bash
python3 skill/jword/tests/test_jword.py      # 18 offline tests
cd skill && zip -r ../dist/jword.zip jword -x '*/__pycache__/*'
```
Guides Claude follows: `references/scoring-rubric.md`, `sources.md`, `contacts.md`, `applicant-profile.md`, `applying.md`, `outreach.md`. Tuning constants are at the top of `scripts/jword.py`.
