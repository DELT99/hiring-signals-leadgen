# Email via Gmail

Use the Gmail connector's draft and send tools (e.g. `create_draft`, `send_message`). If they aren't available, write the email text into the Applications sheet (`message`) and set `draft_ready` with next step "Copy into your email".

## Modes (chosen in Step 3)
| Mode | Jobs mode (applications) | Clients mode (sales outreach) |
|---|---|---|
| Drafts for review (default) | ✓ | ✓ |
| Send each after approval | ✓ (show To, Subject and body first) | ✓ |
| Auto-send | Only to **published careers/HR/recruiting addresses**, **max 10 per run**, one per company | **Not allowed.** Use drafts or approval |

Never email more than **one address per company** per run (the **Email** column's best address) unless the user asks. Don't follow up automatically.

## Job application email (jobs mode)
- **To:** the best address for the job. **Subject:** `Application: <Job Title> – <Full Name>`
- **Body** (≤150 words, facts from the profile only):
  > Dear <Name or "Hiring Team">,
  > I'm applying for the <Job Title> role at <Company> (<job link>). <One sentence matching 2–3 of their requirements to the user's actual experience>. <One sentence on a specific relevant achievement from the CV>.
  > My CV is attached / available at <portfolio or LinkedIn>. I'm available <notice period>.
  > Kind regards, <Full Name> · <phone> · <LinkedIn>
- **CV:** attach `cv_path` if the Gmail tool supports attachments. Otherwise make a **draft** (never send without the CV) with next step **"Attach your CV and send"**.

## Sales outreach email (clients mode)
- **To:** the decision-maker's published address if known, else a hello@/business address. **Subject:** short and specific, e.g. `Flutter help for your mobile roadmap`
- **Body** (≤120 words): why now (they're hiring <role>), what the user offers (one line from the offer), one concrete idea (the **Pitch / Tip**), a low-pressure ask ("Worth a 15-minute call?"), the user's name and company, and an opt-out line: *"If this isn't relevant, just reply 'no' and I won't follow up."*
- Honest and personal. No fake familiarity, no false claims, no tracking tricks. The user is responsible for local rules on commercial email (e.g. CAN-SPAM, GDPR/PECR).

## After each email
Record it with `track`: `emailed` (sent) or `draft_ready` (draft created), with `message` = the body and `next_step` = "Wait for a reply (follow up in ~1 week if you want)" or "Review the draft and send".
