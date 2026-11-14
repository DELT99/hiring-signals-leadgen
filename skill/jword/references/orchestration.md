# Running Jword: one assistant or a team of subagents

Both ways use the same script, rules and outputs. Only the execution differs.

## A. One assistant (Claude chat, Cowork, any app without custom subagents)
Do every stage yourself, in this order, following SKILL.md: inputs → search loop (`next` → search/review/verify) → plan and choices → contacts (about 3 companies per batch) → profile and letters → emails → Gmail → export and report.
- Keep the context lean: write search results straight to the JSON file, and keep summaries in chat to one line per batch.
- Don't load reference files until you reach their stage.

## B. Claude Code with `.claude/agents/` (parallel)
You are the **orchestrator**. You alone talk to the user, own the run state, and perform every external action (Gmail, form submits). Subagents only research or write, then return files.

| Agent | Gets | Returns | Never |
|---|---|---|---|
| `job-researcher` | one `shards` packet (queries + window) | `{query_id: [{title,url,snippet}]}` file | filters by date, invents results, edits state |
| `job-researcher` (verify) | `next --max-tasks 15` open-check tasks | page-check replies file | changes the window |
| `contact-researcher` | 2–4 saved leads (id, company, url, website) | `contacts` updates file | guesses or constructs emails |
| `application-writer` | profile path + 3–5 jobs | `track` updates (status `prepared`) | submits anything |
| `outreach-writer` | profile path + verified contacts + jobs | `outreach` updates file | sends or drafts in Gmail |

### Dependency-aware flow
1. **Inputs** (you) → `init`.
2. **Search, in parallel:** `jword.py shards --workers 3 --per-worker 3`. Launch one `job-researcher` per packet **in the same message**. When all have returned, `ingest --results <packet file>` for each, then `log --agents "job-researcher x3"`.
3. **Review and verify:** `next --batch 12` (review it yourself, since fit judgement stays with the orchestrator), then `next --max-tasks 15`. Split the verify tasks among up to 3 `job-researcher` agents and merge their replies into one file. Where a reply has a `fit_note`, judge it yourself and add a new `fit_score` (drop `fit_note`). Then `apply`. Repeat steps 2–3 until `next` says `done`.
4. **Ask the user** (Step 3 of SKILL.md) → `settings`.
5. **Contacts, in parallel:** split `plan` → `todo.contacts` into groups of 2–4 and give one group to each `contact-researcher` (max 4 at once). Run `contacts --updates` for each file.
6. **Writing, in parallel** (needs steps 4–5): `application-writer` and `outreach-writer` per group of jobs. Record with `track` and `outreach`. Refusals go back to the same writer to fix.
7. **External actions (you only):** `outbox` → Gmail drafts or sends → `gmail` after each call. Forms in the browser per `references/applying.md`.
8. `export`, then `report`.

### Hand-offs go through files, not chat
Write each task to `jword_run/tasks/<agent>-<n>.json` and tell the agent the input and output paths. Have it reply with **one line** ("wrote 23 results to …"). Raw pages and results never enter your context. Use at most 3–4 concurrent agents, and don't spawn an agent for a task with fewer than 2 items: do it yourself.

### Non-negotiables for every agent
The same window (`window` in the packet), no invented data, no relaxing of filters, no external actions. If an agent reports a problem (blocked site, nothing found), record it with `log --error`.

### Cost note
Subagents give separate contexts and parallel speed. They don't automatically use fewer total tokens: each one re-reads its instructions. Use them for genuinely independent, sizeable work (3+ locations, 10+ jobs). For small runs, path A is cheaper.
