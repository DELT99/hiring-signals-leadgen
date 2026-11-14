# Jword scoring rubric

Use this for every `review` candidate. Judge **only** from the candidate's title, snippet and URL, plus the user's offer or CV summary, roles and locations. If something isn't stated, leave the field as `""`; don't guess.

## Fields

| Field | How to fill it |
|---|---|
| `is_job_posting` | `false` if this is a list or search page ("120 Flutter jobs in…"), an article, a company profile or a salary page, rather than **one specific job**. |
| `is_open` | `false` only if the text says the job is closed, expired, filled, removed or no longer accepting applications, or shows a closing date that has passed. Otherwise `true`. |
| `is_agency` | `true` if a recruitment agency is advertising for an unnamed client ("our client…", "X Recruitment is acting as an employment agency"). `false` if the employer itself is hiring, even through a job board. |
| `company` | The hiring company as written in the posting (not the job board). For agency posts, the agency's name. |
| `role` | The job title as written, without extra noise (no "Job Application for", no location). |
| `location` | City and country if shown (e.g. `Berlin, Germany`), or `Remote`. `""` if unknown. |
| `fit_score` | 1–5, using the scale below. |
| `fit_reason` | One short sentence on *why* that score, based on concrete evidence from the posting. |
| `angle` | One sentence. Clients mode: how to pitch this company. Jobs mode: how to tailor the application. |

## Scale: clients mode ("would this company buy what the user offers?")

| Score | Meaning | Example (user = Flutter agency) |
|---|---|---|
| 5 | The hiring need **is** the user's offer | Hiring a Flutter / cross-platform mobile developer |
| 4 | Strong overlap, small gap | Hiring a mobile developer (iOS/Android) for a new app |
| 3 | Related; they could plausibly use the user | Hiring a full-stack dev for a product that has a mobile app |
| 2 | Weak link | Hiring a backend engineer, no mobile mention |
| 1 | Unrelated | Hiring an accountant |

Good `angle` (clients): specific and short, e.g. *"Offer a 2-dev Flutter squad to ship their delivery app's v2 while they keep hiring."* Avoid generic lines like "reach out about services".

## Scale: jobs mode ("does this job fit the candidate?")

| Score | Meaning |
|---|---|
| 5 | Title, core skills, seniority and location all match the CV |
| 4 | Good fit with one gap (e.g. a slightly different stack or one level up) |
| 3 | Partial fit: some core skills match; worth a look |
| 2 | Mostly a mismatch (different stack or far too senior or junior) |
| 1 | Poor fit |

Good `angle` (jobs): *"Lead with your Riverpod + Firebase app that has 10k installs; they mention Firebase twice."*

## Tips
- Be consistent: the same evidence should get the same score across candidates.
- Don't reward keyword stuffing. A snippet that only *lists* the role among many isn't a strong signal.
- If the location clearly contradicts the user's locations (e.g. the posting is in Paris but the user wants London only), still give the honest fit score and put the real location in `location`. The script handles location filtering.
