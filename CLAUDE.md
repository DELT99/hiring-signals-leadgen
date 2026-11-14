# Jword repository: notes for Claude Code

## What this is
Jword, a job-hunting and hiring-signal outreach assistant. The same skill runs in Claude chat (uploaded `dist/jword.zip`) and in Claude Code (this repo).

## Layout and single source of truth
- `skill/jword/` is the **source**: `SKILL.md`, `references/`, `scripts/jword.py` (the deterministic engine), and `tests/`.
- `.claude/skills/jword/` and `dist/jword.zip` are **generated** copies. Never edit them by hand. After any change under `skill/jword/`, run:
  `python3 tools/build_skill.py`
- `.claude/agents/`: the `job-researcher`, `contact-researcher`, `application-writer` and `outreach-writer` subagents (Claude Code only).
- `workflow/`, `src/nodes/`, `scripts/build_workflow.py`, `tests/simulate.js`: the original n8n workflow. Keep it working, and don't mix it with the skill.

## Using Jword here
Type `/jword` or ask "use jword to find …". Follow `SKILL.md`. With subagents available, use `references/orchestration.md` (parallel path). The orchestrator (the main session) alone asks the user, edits run state, and performs Gmail and browser actions. Run state lives in `jword_run/` (git-ignored).

## Tests (run all before committing)
```
python3 skill/jword/tests/test_jword.py
python3 skill/jword/tests/test_jword_v3.py
python3 tests/test_distribution.py
node tests/simulate.js
```

## Rules for changes
- Keep the strict posting-date window, contact verification, outreach checks and send policy inside `jword.py`, and cover each with a test.
- Never commit CVs, profiles, run state, `.env` files or API keys.
- Keep the README beginner-first (Claude chat install before Claude Code).
