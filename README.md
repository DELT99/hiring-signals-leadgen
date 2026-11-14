# Jword: your job hunt and outreach assistant, inside Claude

**A job post means a company needs someone right now.** Jword turns that signal into action. Ask Claude in plain English and it will:

- find **real, open jobs** posted within the window you choose (24 hours to 60 days, or your own dates),
- check that every job is still open and that its posting date really is inside your window,
- find the company's **published** recruiter, HR, founder and generic hiring emails (careers@, jobs@, hr@…), with the page each one came from,
- write a tailored application and **one individual email per contact**, using only facts from your CV,
- create **Gmail drafts** for you to review, or send only with your approval,
- give you an **Excel tracker** and a status table in chat.

> *"Use Jword: find 15 Flutter developer jobs in Germany, the UK or remote, posted in the last 7 days. My CV is attached. Find recruiters and HR emails, write personalized emails, and make Gmail drafts."*

No API keys, no n8n and no coding are needed. It runs on Claude's web search, reasoning, Gmail connector and (optionally) a browser.

**Two ways to use it:**
**[A. Claude chat](#part-a--claude-chat-recommended)** (recommended: upload one zip and you're done) · **[B. Claude Code](#part-b--claude-code-advanced)** (advanced: parallel subagents) · [C. Compare](#part-c--feature-comparison) · [D. Update](#part-d--updating-jword) · [E. Troubleshooting](#part-e--troubleshooting) · [F. n8n workflow](#part-f--optional-n8n-workflow)

---

## How it works
| Stage | What Jword does | You decide |
|---|---|---|
| 1. **Find** | Searches job boards, company career pages and remote boards for every role × location. Drops listing pages, closed or paywalled jobs, duplicates and wrong locations, and **anything outside your posting window or without a verifiable posting date**. Scores each job 1–5 against your CV (with the gaps, honestly) and opens it to confirm it's still accepting applications. | roles, locations, **how recent**, platforms, how many |
| 2. **Contacts** | Finds named recruiters, HR, talent and hiring managers and founders, plus generic hiring inboxes, **only from public pages**, each with its source and a verification status. Never guesses an address. | jobs only / + contacts / + contacts and outreach |
| 3. **Prepare** | Builds your applicant profile from your CV, asks once for anything missing, and writes a cover letter and answers per job. | – |
| 4. **Outreach** | Writes one email per verified contact (own subject, own body), creates Gmail drafts or sends with approval, and records every Gmail id. | contacts only / in chat / **Gmail drafts** / approve each / capped auto |
| 5. **Apply** *(optional)* | Fills application forms in a browser, and hands back to you for logins, CAPTCHAs and uploads. | ask before each submit / auto when covered / fill only |
| 6. **Report** | An Excel tracker (Leads, Contacts, Applications, Run Log, Excluded) plus a status table. | – |

**Clients mode** does the same for agencies and freelancers: companies hiring developers become **sales leads**, with decision-maker contacts and B2B emails. B2B emails are **never** sent automatically.

**The guarantees:** the window is never widened to hit a number · no invented jobs, dates, contacts or experience · emails only to verified, published addresses · never the same email twice, even across runs · nothing is sent or submitted outside the mode you chose · Claude never claims an email was sent without Gmail's confirmation.

---

## Part A — Claude chat (recommended)

**You don't need** VS Code, Git, a terminal, Claude Code, API keys or n8n.

*What's a skill?* A small package of instructions and scripts that teaches Claude a task. You upload it once, and Claude uses it whenever your request matches. ([Claude Help Center: Use skills in Claude](https://support.claude.com/en/articles/12512180))

1. **Download** [`dist/jword.zip`](dist/jword.zip): open it on GitHub → **Download raw file**. **Don't unzip it.**
2. Open **[claude.ai](https://claude.ai)** (or the Claude desktop app).
3. Go to **Customize → Skills**.
4. Click **+ → Create skill → Upload a skill**.
5. Choose `jword.zip`, the zip itself, not an extracted folder.
6. Make sure **Jword** is toggled **on**.
7. Make sure **Code execution and file creation** is on (Settings → Capabilities). It's on by default on most plans; on Team or Enterprise plans an admin may need to enable it.
8. Make sure **Web search** is on in your chat (the tools menu in the message box).
9. *For emails:* **Settings → Connectors → Gmail → Connect**.
10. *For filling forms (optional):* install **Claude in Chrome**, or use the **Claude desktop app**'s built-in browser.
11. Start a **new chat**, attach your CV, and ask, for example:

```text
Use Jword. Find 10 AI Engineer or LLM Engineer jobs, remote, posted in the last 7 days.
My CV is attached. Find recruiter/HR emails and create Gmail drafts for my review.
```
```text
Use Jword to find 20 Flutter developer jobs in Germany, UK and remote worldwide, posted within
the last 14 days. Just the list and the Excel, no emails.
```
```text
Use Jword in clients mode: find companies hiring React developers in Dubai posted this week.
We're a dev agency. Find decision-makers and draft B2B emails in Gmail (no sending).
```
```text
Run Jword again: same search, last 3 days. Here's last week's tracker (attached).
```

Claude asks a few quick multiple-choice questions (including **"How recently should the jobs have been posted?"** and how to handle emails), then works on its own and sends you the Excel file.

In Claude chat, Jword runs as **one assistant**, doing the stages in order and in small batches. You get the same features and checks as in Claude Code. Gmail and form filling work only when those integrations are connected in your chat. Without them, Jword writes the emails in chat and tells you what's missing.

---

## Part B — Claude Code (advanced)

Use this for big runs (many roles and locations). Claude Code runs **specialized subagents in parallel**, each in its own context.

**Prerequisites:** [Claude Code](https://code.claude.com/docs/en/overview) (signed in), [Git](https://git-scm.com/downloads), and Python 3.10+ with `pip install openpyxl`. VS Code is optional.

```bash
git clone https://github.com/DELT99/hiring-signals-leadgen.git
cd hiring-signals-leadgen
code .        # optional: open in VS Code
claude
```
*(Windows: run the same commands in PowerShell or Git Bash. Use `py -m pip install openpyxl` if `pip` isn't found.)*

Claude Code discovers these automatically from the project folder:
| Path | What it is |
|---|---|
| `.claude/skills/jword/SKILL.md` | the Jword skill ([skills docs](https://code.claude.com/docs/en/skills)) |
| `.claude/agents/job-researcher.md` | runs search packets and page checks (Sonnet) |
| `.claude/agents/contact-researcher.md` | finds published contacts (Haiku) |
| `.claude/agents/application-writer.md` | cover letters and answers (Sonnet) |
| `.claude/agents/outreach-writer.md` | one email per contact (Sonnet) |
| `CLAUDE.md` | project notes for Claude |

- **See the agents:** type `/agents` ([subagents docs](https://code.claude.com/docs/en/sub-agents)).
- **Run Jword:** type `/jword`, or just ask: *"Use jword to find 20 Flutter jobs in Germany, UK and remote, posted in the last 7 days."*
- **How it runs:** the main session is the **orchestrator**. It asks you the questions, splits the searches into packets (one per location or role), runs up to 3–4 subagents at once, merges and de-duplicates the results, verifies them, then hands contact research and writing to the other agents. **Only the orchestrator** talks to you, sends Gmail drafts or emails, or submits forms. Subagents have no Gmail, browser or shell access. The same posting window goes to every agent, and the engine enforces it.
- **Models:** set in each agent file (`model: sonnet` / `haiku`). Change one to `inherit` to use your session's model, or set `CLAUDE_CODE_SUBAGENT_MODEL`.
- **Gmail in Claude Code:** the Gmail connector you added in Claude chat isn't automatically available in Claude Code. Add a Gmail MCP server/connector to Claude Code yourself, or let Jword write the emails into the tracker and create the drafts from Claude chat.
- **Cost:** subagents add speed and separate contexts, not guaranteed token savings (each one loads its own instructions). For small runs (one location, ≤10 jobs), Jword stays sequential.

---

## Part C — Feature comparison
| | **Claude chat** | **Claude Code** |
|---|---|---|
| Installation | Upload one zip | Clone the repo, run `claude` |
| Skill support | ✓ | ✓ (`/jword`) |
| Custom subagents | – (one assistant) | ✓ 4 specialized agents |
| Parallel research | – (batched, in order) | ✓ |
| Strict posting-date filter | ✓ | ✓ (same engine) |
| Job verification (open, dated) | ✓ | ✓ |
| Contact research (named + generic) | ✓ | ✓ |
| Application preparation | ✓ | ✓ |
| Gmail drafts / sending | ✓ with the Gmail connector | needs a Gmail connector set up in Claude Code |
| Form filling | ✓ with Claude in Chrome / desktop browser | ✓ with a browser tool |
| Excel tracker | ✓ | ✓ |
| Clients (B2B) mode | ✓ | ✓ |

---

## Part D — Updating Jword
**Claude chat:** download the latest `dist/jword.zip` → **Customize → Skills** → on the old Jword, **⋯ → Delete** → **Upload a skill** with the new zip → toggle it on → start a new chat.

**Claude Code:** `git pull`, then restart `claude` (new agent files can need a restart). Check `/agents` shows the four Jword agents and that `/jword` appears.

---

## Part E — Troubleshooting
| Problem | Fix |
|---|---|
| Skill doesn't appear | Upload the **zip**, not a folder; its top folder must be `jword/` with `SKILL.md` inside. |
| Skill doesn't trigger | Check it's toggled on, start a **new** chat, and say *"Use Jword …"*. |
| "Jword needs web search" | Turn on Web search in the chat's tools menu. |
| No Gmail drafts | Connect Gmail (Settings → Connectors). Until then Jword writes the emails in chat and in the tracker. |
| No Excel file | Turn on *Code execution and file creation*. |
| Claude Code doesn't list the agents | Run `claude` from the repo root; restart after the first pull; check `.claude/agents/*.md` exists. |
| `/jword` not found in Claude Code | Check `.claude/skills/jword/SKILL.md` exists. If you also uploaded Jword in Claude chat, the account copy syncs into Claude Code too, so keep only one (disable the uploaded one, or delete the project copy). |
| Wrong folder structure | Don't move files. The source is `skill/jword/`; `tools/build_skill.py` creates `.claude/skills/jword/` and `dist/jword.zip`. |
| Zip seems out of date | Run `python3 tools/build_skill.py --check`; rebuild with `python3 tools/build_skill.py`. |
| Fewer jobs than asked | Expected when the window is short: Jword never widens it. The Excluded sheet shows why each job was dropped. Try a longer window or more locations. |

---

## Part F — Optional n8n workflow
Prefer hands-off, scheduled lead finding with your own API keys? The original **n8n workflow** is still here. It uses Firecrawl for search and (optionally) Gemini for scoring, and writes to Google Sheets. It finds and scores leads, but doesn't do contacts, emails or applying.
- Import [`workflow/hiring-signal-lead-engine.json`](workflow/hiring-signal-lead-engine.json) into n8n.
- Full setup guide: **[docs/n8n.md](docs/n8n.md)**

---

## Repo layout
```
skill/jword/            SOURCE of the skill: SKILL.md, references/, scripts/jword.py, tests/
.claude/skills/jword/   generated copy for Claude Code (don't edit)
.claude/agents/         the four Claude Code subagents
dist/jword.zip          generated upload for Claude chat (don't edit)
tools/build_skill.py    builds both copies from the source
CLAUDE.md               notes for Claude Code
examples/               sample output
workflow/ src/ sheets/ scripts/ docs/n8n.md   the n8n edition
tests/                  distribution checks + n8n simulator
```

## Development
```bash
python3 tools/build_skill.py                   # after editing skill/jword/
python3 skill/jword/tests/test_jword.py        # engine: search loop, filters, Excel
python3 skill/jword/tests/test_jword_v3.py     # date window, contacts, outreach, Gmail, reruns, packets
python3 tests/test_distribution.py             # zip + Claude Code copy + agents + n8n regression
node tests/simulate.js                         # n8n workflow simulator
```
More detail on stages, sheets and statuses: **[skill/README.md](skill/README.md)**.

## Responsible use
You're responsible for what's sent in your name. Review drafts, and follow local rules for commercial email (CAN-SPAM, GDPR/PECR). Jword never automates LinkedIn, Indeed, Glassdoor or ZipRecruiter applications (their terms forbid it), never solves CAPTCHAs, and never logs in for you.

## License
MIT. See [LICENSE](LICENSE).
