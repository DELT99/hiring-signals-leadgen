# Applying in the browser

**Before you start:** the profile passes `profile-check`, the user has chosen a submit mode (Step 3), and each job has a prepared cover letter and answers (status `prepared`). If a browser skill is listed (`chrome-browser`, `built-in-browser`, `computer-use`), load it first and follow its rules on tabs, permissions and dialogs.

## Which jobs
`python3 SKILL_DIR/scripts/jword.py plan` → `todo.to_apply`. Check `apply_via` for each:

| apply_via | What you do |
|---|---|
| Greenhouse / Lever / Ashby / Workable / Recruitee / Teamtailor / SmartRecruiters / BambooHR / Personio / Breezy / JazzHR form | Fill it (below) |
| Workday / iCIMS form | Usually need an account → `needs_you` ("Create an account and apply: <link>"), with the prepared answers in `message` |
| Company site | Open it. If it leads to one of the forms above, fill it; if it needs a login or account, use `needs_you` |
| Email | Use `references/outreach.md` (job application email) |
| LinkedIn / Indeed / Glassdoor / ZipRecruiter *(apply yourself)* | **Don't automate.** Their terms forbid bots. Set `needs_you`, with the next step "Apply on LinkedIn: <link> (answers ready in the Applications sheet)" |

## Filling a form (one job at a time)
1. Open the job URL in a **new tab**. Confirm it's the right job and still open. If it's closed, use status `skipped` with next step "Closed when checked".
2. Click **Apply**. Fill fields **only from the profile and the prepared answers**: name, email, phone, location, LinkedIn/GitHub/portfolio, work authorization, sponsorship, notice period, salary (the user's exact wording, or "Open to discuss"), cover letter (paste the prepared one).
3. **CV upload:** if the browser tools can upload a local file and `cv_path` exists, upload it. Otherwise **stop on this form**, set `needs_you` with next step *"Upload your CV and press Submit: <Company> form in tab N"*, and move on.
4. **Custom questions:** answer them if the profile clearly covers the answer. Otherwise it's a missing answer: in *ask-before-submit* mode, ask the user; in *auto* mode, set `needs_you` ("Answer: '<question>'") and move on.
5. **Equal-opportunity questions:** follow `eeo_answers` (see applicant-profile.md). Never pick a demographic answer for the user.
6. **Before submitting**, by mode:
   - *Ask before each submit:* show a compact summary (job, the fields you filled, the cover letter's first line, anything left blank) and wait for "submit", "skip" or edits.
   - *Auto when the profile covers everything:* submit only if every required field came from the profile, the CV upload worked (or wasn't required), and nothing is blank or guessed. Otherwise use `needs_you`.
   - *Fill only:* leave the form filled, and set `needs_you` with "Review and press Submit: tab N".
7. **After submitting**, confirm the success page or message ("Thank you for applying"). Record `applied`, with next step "Watch for a reply from <company>". If submission failed, record `failed` with the error.
8. Record **immediately** after each job: `track --updates <file>`.

## Always hand back (`needs_you`) on
A login or account creation, a CAPTCHA or "verify you're human" check, an online test, video interview or personality assessment, a payment request, a request for documents you don't have (transcripts, IDs, references), legal attestations beyond the standard "information is accurate" checkbox, or anything that seems off (a suspicious site, a form asking for bank or ID numbers). Never type passwords. Never solve CAPTCHAs.

## Speed and courtesy
Apply to one job at a time, and don't open more than about 3 tabs at once. Don't resubmit after a failure without asking. If a site shows rate-limit or bot warnings, stop applying there and use `needs_you`.
