# Finding company contacts and published emails

**Goal:** for every shortlisted company, collect **all genuinely useful published contacts**, not just one inbox:
- **Named:** recruiters, technical recruiters, HR, Talent Acquisition, recruitment/hiring managers, and founders or CTOs when they hire directly.
- **Generic:** careers@, jobs@, hr@, recruitment@, hiring@, talent@, people@, and info@ or contact@ as a fallback.

**Rule:** an address counts only if you **saw it published on a public page**. Record the page (`source_url`) and the quoted text that contains it (`evidence`). `jword.py contacts` refuses anything else.

## Two stages (the script enforces the second)
1. **Job post + listing**: often enough for agencies and small companies that print "send your CV to …".
2. **Company website**: **required whenever stage 1 found no verified recruiter, HR or careers/jobs/hr address** (an info@ alone isn't enough). Search the company by name, find its own domain, and check its careers, contact, about and team pages. `plan` gives ready `contact_queries` for each job. `contacts` keeps a lead under `incomplete` until you send it again with `website` (or `no_website: true`).

## Where to look (about 4–6 fetches per company)
**Open pages through search results.** Claude's web fetch usually refuses URLs that didn't come from a search result or the user. So don't type `acme.com/careers` straight into a fetch: search first (`acme.com careers`, `acme.com contact`, `"Acme" careers email`), then fetch the result links. Search snippets often show the address already.

1. **The job posting:** "send your CV to …". Addresses in search snippets are captured automatically.
2. **The official website.** Use the job URL's domain if it's the company's own. Otherwise web-search `"<Company>" official site` and pass it as `website` (this lets the script verify addresses published there). Then fetch:
   `/careers` `/jobs` `/join-us` → hiring inboxes · `/contact` → hello@, info@ · `/about` `/team` `/people` → named people (sometimes with their emails) · `/press` → press releases that name HR or founders.
3. **Search for published addresses:** `"@<domain>" careers OR jobs OR hr OR recruiting OR talent`, and `"<Company>" recruiter OR "talent acquisition" OR "head of people"`. Use a result only if its text shows the full address, or the person's name and role at this company.
4. **Named people without a public email** still help (the user can find them on LinkedIn themselves). Record them under `people`, with the page that names them.

## What to record
```json
[{"id": "c12", "website": "https://acme.com",
  "emails": [
    {"email": "careers@acme.com", "source_url": "https://acme.com/careers", "evidence": "Questions? Write to careers@acme.com"},
    {"email": "sara.khan@acme.com", "name": "Sara Khan", "role": "Head of Talent",
     "source_url": "https://acme.com/team", "evidence": "Sara Khan – Head of Talent – sara.khan@acme.com"}],
  "people": [
    {"name": "Omar Ali", "role": "Founder & CTO", "source_url": "https://acme.com/about", "evidence": "Founded in 2021 by Omar Ali (CTO)"}]}]
```
Run `python3 SKILL_DIR/scripts/jword.py contacts --updates contacts.json`. If you found nothing, send `{"id": "c12", "emails": []}` so the job is marked as checked. Then tell the user honestly that no published email exists, and that the form is the way in.

## Verification (done by the script)
| Shown as | Meaning | Emailed? |
|---|---|---|
| Verified: in the job post | printed in the posting itself | yes |
| Verified: company website | the page is on the company's own domain, or the address's domain matches the page's | yes |
| Verified: company ATS page | published on the company's Greenhouse, Lever or similar page | yes |
| Unverified: third-party page | found on an unrelated site (directories, aggregators, blogs) | **no** |
| No public email (named contact only) | person confirmed, no address | no |

A named address without a name attached is shown as *Named (identity unconfirmed)*. The same address found for several jobs becomes **one** Contacts row listing all of those jobs.

## The script refuses
- Missing `source_url`, or `evidence` that doesn't contain the exact address: **no guessing**. No `first.last@domain` patterns, no "email finder" results, no addresses built from a name and a domain.
- Personal mailboxes (gmail, outlook…) unless the job posting lists them; `noreply@` addresses; sample addresses such as `name@company.com`.

## Traps seen in live runs
- **The job board's own address** (support@taraki.co, support@qureos.com, jobcrawls@gmail.com) is not the employer's. Don't record it. The script also refuses a job board's domain as the company `website`.
- **`[email protected]`** is Cloudflare hiding the real address. You can't use it; look for the address in a search snippet instead.
- **Email-pattern sites** (prospeo, Apollo, RocketReach, Hunter, autotouch "email format" pages) show *guessed* formats like `john.doe@acme.com`. Never use them. The script rejects addresses that aren't quoted in the evidence.
- **Recruiter posts naming a personal mailbox** (hotmail, gmail) are acceptable only if it is the address the job post itself says to apply to.
- **An honest "no public email"** is a normal result: about half the companies in live tests published none. Say so, and point to the application form.

## Don't
Log in anywhere, open LinkedIn pages, use paid email-finder sites, bypass any access restriction, or collect phone numbers, home addresses or personal social accounts.

## Which address the Leads sheet shows
The best **verified** one: a named recruiter or HR person, then a careers/jobs/HR/talent inbox, then another named person, then hello@ or info@. Every contact is listed in the **Contacts** sheet.
