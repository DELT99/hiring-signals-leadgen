// Build AI Prompt
// Builds the Gemini request that qualifies one job posting.
// Clients mode: "would this company buy what I offer?"  Jobs mode: "does this job fit my CV?"

const lead = $input.first().json;
const cfg = lead.config;
const form = lead.form;
const isClients = lead.mode === 'clients';

// Rate-limit Gemini calls
const gap = Date.now() - Number(lead.lastAiCallAt || 0);
const minGap = Number(cfg.aiMinIntervalMs || 4500);
if (gap < minGap) await new Promise((r) => setTimeout(r, minGap - gap));

const offer = String(form['What you offer / your CV summary'] || '').slice(0, 2000);

const task = isClients
  ? `You qualify B2B sales leads. A company that posts a job opening is a potential client for the user.
The user offers: """${offer}"""
Score how likely this company would buy the user's services, based on what it is hiring for.
5 = the hiring need matches the offer exactly; 3 = related; 1 = unrelated.`
  : `You screen job postings for a job seeker.
Candidate profile: """${offer}"""
Score how well this job fits the candidate (skills, seniority, location).
5 = excellent fit; 3 = partial fit; 1 = poor fit.`;

const prompt = `${task}

Search result to evaluate:
Board: ${lead['Job Board']}
URL: ${lead['Job URL']}
Title: ${lead.rawTitle || ''}
Snippet: ${lead.Snippet}
Target role keywords: ${form['Role or skill keywords'] || ''}
Target location: ${form.Location || ''}

Rules:
- Use only the information above. Do not invent facts; use "" when unknown.
- is_job_posting = false if this is a list or search page, an article, or a company page rather than one specific job.
- company, role, location: as stated in the posting.
- fit_reason: one short sentence.
- angle: ${isClients ? 'one sentence on how to pitch this company' : 'one sentence on how to tailor the application'}.`;

const geminiBody = {
  contents: [{ role: 'user', parts: [{ text: prompt }] }],
  generationConfig: {
    temperature: 0.2,
    responseMimeType: 'application/json',
    responseSchema: {
      type: 'OBJECT',
      properties: {
        is_job_posting: { type: 'BOOLEAN' },
        company: { type: 'STRING' },
        role: { type: 'STRING' },
        location: { type: 'STRING' },
        fit_score: { type: 'INTEGER' },
        fit_reason: { type: 'STRING' },
        angle: { type: 'STRING' },
      },
      required: ['is_job_posting', 'company', 'role', 'location', 'fit_score', 'fit_reason', 'angle'],
    },
  },
};

return [{ json: { ...lead, geminiBody, lastAiCallAt: Date.now() } }];
