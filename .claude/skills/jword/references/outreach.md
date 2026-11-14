# Personalized outreach and Gmail

Two separate kinds of email, each with its own rules:
- **Job-seeking** (jobs mode): the user writing to a company about a real open job.
- **B2B sales** (clients mode): the user offering services to a company that's hiring. These are **never** sent automatically.

## 1. Write one email per recipient
For each verified contact the user wants emailed (Contacts → *Verified*), write an individual email:
- **Subject:** unique to this job and company, e.g. `Flutter Developer role at Acme – Talha Tariq`. Never reuse a subject across companies.
- **Greeting:** a named contact gets their name ("Hi Sara,"). A generic inbox gets "Hello Acme hiring team," (never "Dear Sir/Madam").
- **Body (≈90–180 words):**
  1. Why you're writing: the specific job (with its title, and a link if natural).
  2. Two or three of the job's real requirements, matched to the user's **actual** experience from the CV (projects, tools, results). Name any gap honestly, or leave it out; never paper over it.
  3. Something true and specific about this company **taken from the job post or their site** (what they build, the stack in the listing). Don't invent research, mutual contacts or earlier conversations.
  4. A natural ask: "Would you be open to a short call?" or "Happy to share more if it helps."
  5. Sign-off with the user's name and one or two links (portfolio, GitHub, LinkedIn) from the profile.
- **Recipient-aware:** a recruiter cares about fit and availability; a founder or CTO cares about what you'll build; a generic inbox needs the job title early so it gets routed.
- **B2B:** why now (they're hiring <role>), one concrete idea, the user's offer in one line, a low-pressure ask, and an **opt-out line** ("If this isn't relevant, just say so and I won't follow up."). The user is responsible for commercial-email rules (CAN-SPAM, GDPR/PECR).
- Plain, natural English. No buzzword stacks ("passionate, results-driven, synergy"), no flattery, no exaggeration, no placeholders.

Record the emails: `python3 SKILL_DIR/scripts/jword.py outreach --updates emails.json`
```json
[{"id": "c12", "to": "sara.khan@acme.com", "subject": "Flutter Developer role at Acme – Talha Tariq",
  "body": "Hi Sara,\n\n...", "attach_cv": true}]
```
The script refuses: recipients that aren't recorded and verified contacts for that job, missing or very short bodies, unfilled placeholders like `[Company]`, a subject already used for another company, a body ≥82% identical to another company's email, B2B emails without an opt-out line, and addresses already contacted in this or an earlier run. Override a repeat only if the user explicitly says so (`"override_duplicate": true`).

## 2. Show, then act within the chosen mode
Show the user a short list (company → recipient → subject). Then run `jword.py outbox`. Each item's `allowed` field says what you may do:

| allowed | Do this |
|---|---|
| `none` | Modes *contacts only* / *chat*: show the email text in chat. Nothing goes to Gmail. |
| `draft` | Gmail `create_draft` (to, subject, plain-text body). |
| `send_after_approval` | Show that email in full, wait for an explicit "send", then `send_message` (or send the draft by `draftId`). |
| `send` | *Capped auto* mode, job applications to verified hiring addresses: `send_message`. The cap is 10 per run; after that, approval is needed again. |

**Attaching the CV:** the Gmail tools accept attachments as a file reference: `{"content": "sha256:<hash>:<absolute path>", "filename": "CV.pdf", "mimeType": "application/pdf"}` (get the hash with `sha256sum <file>`). If you can't attach it, create a **draft** and set the next action *"Attach your CV and send"*. Never send a job application without the CV unless the user says so.

## 3. Record every Gmail result immediately
```json
[{"oid": "o3", "action": "draft", "ok": true, "id": "r-8812345"},
 {"oid": "o4", "action": "send", "ok": true, "id": "18c2f...", "approved_by_user": true},
 {"oid": "o5", "action": "draft", "ok": false, "error": "Gmail connector not connected"}]
```
`python3 SKILL_DIR/scripts/jword.py gmail --updates gmail.json`
- `id` is the draft or message id **returned by the connector**. Without it, the script records a failure.
- A send outside the chosen mode, a send without approval in approve-each mode, and a second send of the same email are all refused.
- If Gmail isn't connected: say so once, keep the emails in the Applications sheet (`chat` mode), and explain how to connect it (Settings → Connectors → Gmail).

## Don'ts
No follow-up sequences, no mass mail, no tracking pixels, no BCC lists, no sending from aliases. Don't claim anything was sent unless `gmail` recorded it.
