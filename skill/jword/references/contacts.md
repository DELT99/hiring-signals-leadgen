# Finding company contact emails

**Goal:** for each saved job, the best published address to reach the hiring team, plus any other relevant published addresses.
**Rule:** an address counts only if you **saw it on a public page**. Record the page (`source_url`) and the text that shows it (`evidence`). `jword.py contacts` refuses anything else.

## Where to look, in order (stop once you have a good one)
1. **The job posting** itself: "send your CV to careers@…". Addresses printed in a search snippet are captured automatically.
2. **The company website.** Find the official site first: the job URL's domain if it's the company's own, otherwise web-search `"<Company>" official website`. Then web-fetch the pages that usually list addresses:
   - `/careers`, `/jobs`, `/join-us`, `/work-with-us` → careers@, jobs@, recruiting@, talent@
   - `/contact`, `/contact-us` → hello@, info@, contact@
   - `/about`, `/team`, `/company`, `/people` → named leaders (founder, CTO, Head of Talent) and sometimes their addresses
   - `/press`, `/media` → press@ (low priority)
3. **Web search for published addresses:** `"@<domain>" careers OR jobs OR hr OR recruiting OR talent`, and `"<Company>" "careers@" OR "jobs@" OR "hr@"`. Only use a result if its text shows the full address.
4. **People** (founders, HR, recruiters, hiring managers): find names and titles from the team page or search results (like the `contact` step). Record a person's email **only if it's published** (on the company site, in a press release, or in the job post). Otherwise record the person as a contact without an email.

## What to expect
Many companies **don't publish any email**. They use an application form or a "join our talent pool" form instead (live test: Waracle). That's a normal result: record `{"id", "emails": []}`, and the form remains the way to apply. Some sites refuse to be fetched; if that happens, rely on search results that show the address, and don't retry the same page.

## What to record
```json
[{"id": "c12", "website": "https://acme.com",
  "emails": [
    {"email": "careers@acme.com", "source_url": "https://acme.com/careers", "evidence": "Questions about a role? Write to careers@acme.com"},
    {"email": "sara.khan@acme.com", "name": "Sara Khan", "role": "Head of Talent",
     "source_url": "https://acme.com/team", "evidence": "Sara Khan – Head of Talent – sara.khan@acme.com"}
  ]}]
```
`python3 SKILL_DIR/scripts/jword.py contacts --updates contacts.json`. If you found nothing, send `{"id": "c12", "emails": []}` so the job is marked as checked.

## The script refuses
- No `source_url`, or `evidence` that doesn't contain the exact address: **no guessing**. That rules out patterns like `first.last@domain`, "email finder" guesses, or addresses inferred from someone else's.
- Personal mailboxes (gmail, outlook, yahoo…) unless the **job posting** lists them.
- `noreply@` / `do-not-reply@` addresses.

## Don't
- Don't log in anywhere, open LinkedIn pages, or use paid "email finder" sites.
- Don't collect phone numbers, home addresses or personal social accounts.
- Don't spend more than about 4 fetches per company. If nothing turns up, move on.

## Which address is used
The **Email** column shows the best one: a named recruiter or HR person, then a careers/jobs/HR/talent-style address, then another person, then hello@/info@. All addresses are listed in the **Contacts** sheet with where each was found.
