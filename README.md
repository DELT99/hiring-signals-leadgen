# Jword: your job hunt and lead-gen assistant, inside Claude

**A job post means a company needs someone right now.** Jword turns that signal into action. Ask Claude in plain English and it finds open jobs that fit you, finds who to contact, prepares tailored applications, and applies for you, step by step and with your approval.

> *"Use Jword: find 10 Flutter developer jobs in Berlin or remote that fit my CV (attached), get the HR emails, and apply."*

**No API keys, no n8n, no setup.** It runs on Claude's own web search, reasoning and browser.

## The goal
Job hunting and B2B prospecting share the same slow loop: search boards, open dozens of stale postings, find out who to contact, rewrite the same answers, fill the same forms, then lose track. Jword automates that loop and keeps **you in control** of anything sent in your name:

- **Only real, open jobs:** closed, expired, duplicate and agency-hidden postings are filtered out, and each shortlisted job is opened to confirm it's live.
- **Only real contacts:** emails are taken from the company's own public pages, with the source recorded. Nothing is guessed.
- **Only your real details:** applications are written from your CV. Anything missing is asked for, never invented.
- **One tracker:** an Excel file plus a status list in chat (Applied · Needs you · Emailed · Skipped), with the next step for each job.

## What it does
| Stage | Jword… | You choose |
|---|---|---|
| 1. **Find** | searches the open web for every role × location, filters stale, listing and agency posts, scores each job 1–5 against your CV, and checks it's still open | roles, locations, platforms, how many (10 or 25) |
| 2. **Contacts** | finds published careers/HR/recruiter/founder emails on company pages | do it or skip |
| 3. **Prepare** | builds your applicant profile and writes a cover letter and answers per job | do it or skip |
| 4. **Apply** | fills forms in the browser and/or emails applications via Gmail | *ask before each submit*, *auto when everything's covered*, or *fill only*; Gmail *drafts*, *approve each* or *capped auto-send* |
| 5. **Report** | Excel tracker + status table with next steps | – |

It also has a **clients mode** for agencies and freelancers. The same engine treats companies that are hiring as **sales leads**, finds decision-makers and drafts outreach.

## Quick start (about 2 minutes)

**New to Claude skills?** A *skill* is a small package of instructions and scripts that teaches Claude a task. You upload it once, and Claude uses it automatically whenever your request matches.

1. **Download** [`dist/jword.zip`](dist/jword.zip): open it on GitHub, click **Download raw file**, and **don't unzip it**.
2. **Upload it to Claude:** go to **Customize → Skills → + → Create skill → Upload a skill**, choose `jword.zip`, and make sure it's toggled **on**.
3. **Turn on what it needs:**
   - **Web search** in your chat (required)
   - **A browser** to fill application forms: the **Claude in Chrome** extension, or the **Claude desktop app**'s built-in browser
   - **Gmail** to email applications: **Settings → Connectors → Gmail**
4. **Ask.** For example:
   - *"Find 10 AI engineer jobs in London or remote that fit my CV."* (attach your CV)
   - *"Find 25 Flutter jobs on company career pages in Germany. Just the list."*
   - *"Find companies hiring React developers in Dubai. We're a dev agency. Draft outreach in Gmail."*
   - *"Run Jword again"* + attach last time's Excel: no repeats, and the tracker carries on.

Claude asks a few quick multiple-choice questions, then works on its own. To **update** Jword, delete the old skill in *Customize → Skills* (**⋯ → Delete**) and upload the new zip.

<details>
<summary>Good to know</summary>

- Skills need *Code execution and file creation* on. It's on by default on most plans; on Team/Enterprise plans an admin may need to enable it.
- Skills you enable in Claude also load in **Claude Code** when you sign in with the same account.
- Each run uses your Claude plan's usage. Applying is the heaviest step, so start with 2–3 jobs in *ask before each submit* mode.
</details>

## What you get
An Excel file with four sheets:
- **Leads:** company, job, location, posted, source, link, fit score, *why it fits*, pitch/tip, contact, **email**, **apply via**, **status**, **next step**
- **Contacts:** every email found, with the page it came from
- **Applications:** status, next step, and the cover letter and answers used
- **Run Log:** what was searched and what was filtered out and why

…plus a **status table in chat**, so you know exactly what's done and what still needs you.

## Built-in guardrails
- **Hands back to you:** logins, CAPTCHAs, assessments, unanswered questions, and CV uploads Claude can't do. You get the exact next step, e.g. *"Upload your CV and press Submit: tab 3"*.
- **Never automates LinkedIn, Indeed, Glassdoor or ZipRecruiter applications**, because their terms forbid it. You get the link and prepared answers instead.
- **Never auto-sends cold sales email.** Job-application emails go only to published careers/HR addresses, with a cap per run.
- **You're responsible** for what's sent in your name and for local email rules (e.g. GDPR, CAN-SPAM). Review drafts before sending.

Full details are in the **[Jword guide](skill/README.md)**.

---

## Other option: the n8n workflow
Prefer **hands-off automation** with your own API keys? This repo also includes the original **n8n workflow**. It runs on a schedule, uses Firecrawl for search and Gemini for scoring (optional), and writes leads to a Google Sheet. It finds and scores leads, but doesn't apply or email.

- Import [`workflow/hiring-signal-lead-engine.json`](workflow/hiring-signal-lead-engine.json) into n8n.
- Setup guide (credentials, Google Sheet, node wiring, troubleshooting): **[docs/n8n.md](docs/n8n.md)**

| | **Jword (Claude skill)** | **n8n workflow** |
|---|---|---|
| Setup | Upload one zip | n8n + Firecrawl + Gemini + Google OAuth |
| Finds & scores jobs/leads | ✓ | ✓ |
| Contact emails, applying, Gmail | ✓ | – |
| Runs on a schedule | – (when you ask) | ✓ |
| Output | Excel + chat status list | Google Sheet |

## Repo layout
```
skill/jword/        the Claude skill (SKILL.md, guides in references/, engine in scripts/, tests/)
dist/jword.zip      the upload-ready skill
examples/           sample output from a live run
workflow/, src/, sheets/, scripts/, tests/, docs/n8n.md   the n8n edition
```

## Development
```bash
python3 skill/jword/tests/test_jword.py                           # skill: 18 offline tests
cd skill && zip -r ../dist/jword.zip jword -x '*/__pycache__/*'   # rebuild the upload zip
npm test                                                          # n8n edition: workflow simulator
```

## License
MIT. See [LICENSE](LICENSE).
