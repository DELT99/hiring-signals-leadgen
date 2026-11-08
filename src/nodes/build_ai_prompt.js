// Build AI Prompt
// Builds the Gemini request that qualifies one job posting. Also handles retry pacing:
// on a retry it waits (exponential backoff, or Gemini's own retryDelay) and may use a fallback model.

const lead = $input.first().json;
const cfg = lead.config;
const form = lead.form;
const isClients = lead.mode === 'clients';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const models = cfg.aiModels && cfg.aiModels.length ? cfg.aiModels : ['gemini-3.5-flash-lite'];
const modelIdx = Math.min(Number(lead.aiModelIdx ?? lead.aiModelIdxRun ?? 0), models.length - 1);
const model = models[modelIdx];
const attempt = Number(lead.aiAttempt || 0);

// Backoff before a retry
if (attempt > 0) {
  const backoff = lead.aiRetryDelayMs || Math.min(2000 * 2 ** (attempt - 1), 20000);
  await sleep(backoff);
}
// Rate-limit all Gemini calls
const gap = Date.now() - Number(lead.lastAiCallAt || 0);
const minGap = Number(cfg.aiMinIntervalMs || 4500);
if (gap < minGap) await sleep(minGap - gap);

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
Target roles (any of): ${cfg.rolesText || ''}
Target locations (any of): ${cfg.locationsText || ''}

Rules:
- Use only the information above. Do not invent facts; use "" when unknown.
- is_job_posting = false if this is a list or search page, an article, or a company page rather than one specific job.
- is_open = false only if the text says the job is closed, expired, filled or no longer accepting applications; otherwise true.
- company, role, location: as stated in the posting (location = city and country, or "Remote").
- fit_reason: one short sentence.
- angle: ${isClients ? 'one sentence on how to pitch this company' : 'one sentence on how to tailor the application'}.`;

const generationConfig = {
  temperature: 0.2,
  maxOutputTokens: 512,
  responseMimeType: 'application/json',
  responseSchema: {
    type: 'OBJECT',
    properties: {
      is_job_posting: { type: 'BOOLEAN' },
      is_open: { type: 'BOOLEAN' },
      company: { type: 'STRING' },
      role: { type: 'STRING' },
      location: { type: 'STRING' },
      fit_score: { type: 'INTEGER' },
      fit_reason: { type: 'STRING' },
      angle: { type: 'STRING' },
    },
    required: ['is_job_posting', 'is_open', 'company', 'role', 'location', 'fit_score', 'fit_reason', 'angle'],
  },
};
// Thinking makes simple scoring slow (the cause of 60s timeouts). Gemini 3+ uses thinkingLevel,
// Gemini 2.x uses thinkingBudget. Dropped automatically if a model rejects it.
if (!lead.aiNoThinking && !lead.aiNoThinkingRun) {
  generationConfig.thinkingConfig = /^gemini-2/.test(model)
    ? { thinkingBudget: 0 }
    : { thinkingLevel: cfg.aiThinkingLevel || 'minimal' };
}

const geminiBody = { contents: [{ role: 'user', parts: [{ text: prompt }] }], generationConfig };

return [{
  json: {
    ...lead,
    aiModelIdx: modelIdx,
    aiModelCurrent: model,
    geminiBody,
    lastAiCallAt: Date.now(),
  },
}];
