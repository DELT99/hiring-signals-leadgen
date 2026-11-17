# Where Jword finds jobs

Jword plans its searches the way the n8n agent does, using only Claude's own web search (no API keys). The user's answers become a list of **boards**, and each search targets one board with a `site:` filter. Live tests showed that Claude's web search honours `site:` for job boards and ATS domains (rozee.pk, hired.pk, greenhouse.io, workable.com, remotive.com…).

| Board | Query shape | What comes back |
|---|---|---|
| Open web | `Flutter Developer jobs Lahore posted 2 days ago` | Company pages, Built In, aggregators |
| LinkedIn hiring posts | `site:linkedin.com "hiring" "AI Engineer" remote` | Posts such as "We're hiring… send your CV to talent@…". LinkedIn's `/jobs/view/` pages are **not** in the index, and LinkedIn pages are never fetched |
| Regional boards (location's country) | `site:rozee.pk "Flutter Developer" Lahore "Nov" "2026"` | Rozee.pk, Hired.pk, Taraki (Pakistan); Bayt (UAE, Saudi Arabia, Qatar); Wuzzuf (Egypt); Naukri (India); Reed and Totaljobs (UK); StepStone (Germany); Built In (US) |
| Career-page systems | `site:greenhouse.io "Flutter Developer" remote` | Greenhouse, Workable, Lever, Ashby: employer named, apply form |
| Remote boards (remote roles) | `site:remotive.com/remote/jobs "AI Engineer" remote` | Remotive, DailyRemote, Arc, We Work Remotely |

**How searches are shared out (n8n parity):**
- Every role × location gets a turn.
- Each search goes to the board that is furthest behind its share. LinkedIn has a weight of 1.4, so it gets roughly one search in three.
- A board that returns nothing new twice in a row is skipped.
- Regional boards only serve their own country.
- The run stops when one of these happens:
  - the target is reached;
  - the search budget is used up (`min(36, 2.5 × target + combos + 2)`);
  - many searches in a row saved nothing.
- Rejected results don't count toward that last condition. A search full of old pages is only one dry search.

**Date words.** Dated boards print the posting date on every listing ("Posting Date: Nov 09, 2026"). For these boards the query includes this month's words, `"Nov" "2026"` (plus last month's when the window spans two months). The index then returns fresh listings with the date in the snippet. In a live test on Rozee, the plain query returned listings from 2023 to 2025. The date-anchored query put this month's three listings first.

## Boards that show posting dates (best for strict windows)
- Remotive: "Posted 2d ago"
- Wellfound: "Posted: 2 days ago"
- Arc: "Posted a day ago"
- DailyRemote
- Built In: "Posted 2 Days Ago"
- Rozee.pk: "Posting Date: Nov 09, 2026"
- Hired.pk: "Date: 6 hours ago"
- Taraki: "5 days ago"
- Mustakbil: "Posted yesterday"
- `apply.workable.com/…/jobs/view/….md` pages: "Posted 2026-08-05"
- LinkedIn post ages: "2d •"

Greenhouse, Lever, `jobs.workable.com` and many company pages show **no** date. With a strict window those jobs are dropped unless a search snippet carries a date. To keep them, run with `--undated separate`. They are then listed apart and marked *date not verified*, never mixed into the dated results.

## What gets filtered
| Filter | Examples |
|---|---|
| Listing / search / salary pages | "Flutter Developer Jobs in London", "54,244 Flutter Developer Jobs", `/find/…`, `?q=`, `.do` stats pages |
| Not this role | Titles and snippets must mention the role. Variants count: "AI/ML Engineer", "Artificial Intelligence Engineer" and "AI Solutions Engineer" all match *AI Engineer*; "Air conditioning engineer" doesn't |
| Closed or stale | "already been filled", "deactivated by the company's administrator", "no longer available", "Closes 01 Jan 2025" (date passed), older than *Posted within* |
| Sidebar dates | "Similar jobs … Posted Nov 07" is ignored; only the job's own date counts |
| Wrong location (strict mode) | Manchester when only London was asked |
| Agency posts (clients mode) | "our client…", "acting as an employment agency" |
| Duplicates | Same URL, or same company + job title (also against an earlier Jword file) |

## Variety
LinkedIn may supply up to about **40%** of the leads and any other website about **a third** (`source_cap`). After 4 searches, if enough qualified leads are already waiting, the cap is relaxed so the run can finish without wasting searches.

## Tuning
Edit the constants at the top of `scripts/jword.py`:
- `BOARD_CATALOG`, `REGIONAL_BOARDS` and `PLATFORM_BOARDS`
- `QUERY_STYLES`, `CLOSED_PHRASES`, `LISTING_URL` / `LISTING_TITLE`
- `AGENCY_HINTS`, `LOCATION_GROUPS`, `ROLE_SYNONYMS`

Then run both test files in `tests/`.
