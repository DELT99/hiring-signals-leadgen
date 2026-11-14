# Where Jword finds jobs

Jword searches the **open web** with natural queries such as `Flutter Developer job London hiring November 2026`, rotating through 5 query styles for every role × location. In testing, Claude's web search did **not** honour `site:` filters, so Jword doesn't target specific job boards. Typical sources are:

- **Company career pages and applicant-tracking systems:** Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, Personio, SmartRecruiters. These are the best leads: the employer is named and the page check works well.
- **Tech job boards:** Built In, Welcome to the Jungle, WeAreDevelopers, Wellfound, Dice, Remote OK…
- **Aggregators and recruiter sites:** IT Jobs Watch, Career.io, Jooble, Gumtree, GrabJobs… Often agency posts (skipped in clients mode) or copies of the same job (de-duplicated by company + title).
- **LinkedIn / Indeed:** they appear only occasionally in web search. LinkedIn pages are never fetched.

## What gets filtered
| Filter | Examples |
|---|---|
| Listing / search / salary pages | "Flutter Developer Jobs in London", "54,244 Flutter Developer Jobs", `/find/…`, `?q=`, `.do` stats pages |
| Closed or stale | "already been filled", "job was removed", "no longer available", "Closes 01 Jan 2025" (date passed), older than *Posted within* |
| Wrong location (strict mode) | Manchester when only London was asked |
| Agency posts (clients mode) | "our client…", "acting as an employment agency" |
| Duplicates | Same URL, or same company + job title (also against an earlier Jword file) |

## Variety
No single website may supply more than about **a third** of the leads (`source_cap`). After 4 searches, if enough qualified leads are already waiting, the cap is relaxed so the run can finish without wasting searches.

## Tuning
Edit the constants at the top of `scripts/jword.py`: `QUERY_STYLES`, `CLOSED_PHRASES`, `LISTING_URL` / `LISTING_TITLE`, `AGENCY_HINTS`, `LOCATION_GROUPS`, `SOURCE_NAMES`. Then run `python3 tests/test_jword.py`.
