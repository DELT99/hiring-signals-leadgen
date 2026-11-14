# Applicant profile

Build this once from the user's **CV** (attached PDF/DOCX: read it) and/or what they tell you. Save it as `applicant_profile.json` in the working folder, then run:

```bash
python3 SKILL_DIR/scripts/jword.py profile-check --profile applicant_profile.json
```

Ask for everything listed as `missing` in **one** message, using options for yes/no items. **Never fill a field with a guess.** At the end, offer the user the file so they can attach it next time.

```json
{
  "full_name": "", "email": "", "phone": "",
  "location": "City, Country",
  "linkedin": "", "github": "", "portfolio": "",
  "cv_path": "<path of the attached CV file, if any>",
  "headline": "e.g. Flutter developer, 3 years, fintech apps",
  "summary": "3-4 sentences from the CV",
  "skills": ["Flutter", "Dart", "Firebase"],
  "experience": [{"company": "", "title": "", "from": "YYYY-MM", "to": "YYYY-MM or present", "highlights": [""]}],
  "education": [{"school": "", "degree": "", "year": ""}],
  "work_authorization": {"<country>": "Citizen | Permanent resident | Visa holder | Needs visa"},
  "needs_sponsorship": false,
  "willing_to_relocate": "yes | no | depends",
  "remote_preference": "remote | hybrid | onsite | any",
  "notice_period": "e.g. 1 month",
  "earliest_start": "",
  "salary_expectation": "e.g. EUR 60,000 per year, or 'Open to discuss'",
  "languages": ["English (fluent)"],
  "standard_answers": {
    "why_this_company": "write per job, from the posting plus the profile",
    "anything_else": ""
  },
  "eeo_answers": "decline | ask",
  "cover_letter_style": "short and direct | warm | formal"
}
```

**Required for applying:** `full_name`, `email`, `phone`, `location`, `work_authorization`, `needs_sponsorship`, `notice_period`, `salary_expectation`, plus **either** `cv_path` (a CV file) **or** both `experience` and `skills`.

**No CV file?** Claude can still fill most forms from the details, but forms that **require** a CV upload are marked **Needs you: upload CV**, with the form left open.

**Equal-opportunity and diversity questions** (gender, ethnicity, disability, veteran status): with `"eeo_answers": "decline"`, pick "Prefer not to say" or "Decline to self-identify" when that option exists, otherwise hand the question back. With `"ask"`, always hand back. Never answer these on the user's behalf.
