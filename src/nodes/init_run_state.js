// Init Run State
// Reads the form, sets up configuration and the loop's state object.
// Edit CONFIG below to tune the workflow without touching other nodes.

const CONFIG = {
  aiModel: 'gemini-3.7-flash',      // any Gemini model that supports generateContent
  aiMinIntervalMs: 4500,            // minimum gap between Gemini calls (free-tier friendly)
  firecrawlDelayMs: 700,            // pause between Firecrawl searches
  maxConsecutiveApiErrors: 3,       // stop the run if Firecrawl keeps failing
  contactRoles: [
    'CTO', '"Head of Engineering"', '"Engineering Manager"', 'Founder', 'CEO',
    '"Talent Acquisition"', '"HR Manager"',
  ],
  // Job boards: site filter for the query + regex a single posting URL must match.
  boards: {
    'LinkedIn Jobs': { site: 'linkedin.com/jobs/view', match: 'linkedin\\.com\\/jobs\\/view\\/' },
    'Rozee.pk':      { site: 'rozee.pk', match: 'rozee\\.pk\\/' },
    'Indeed':        { site: 'indeed.com', match: 'indeed\\.com\\/' },
    'Bayt':          { site: 'bayt.com', match: 'bayt\\.com\\/[a-z]{2}\\/.*job' },
    'Greenhouse':    { site: 'greenhouse.io', match: 'greenhouse\\.io\\/[^/]+\\/jobs\\/\\d+' },
    'Lever':         { site: 'jobs.lever.co', match: 'jobs\\.lever\\.co\\/[^/]+\\/[0-9a-f-]{8,}' },
    'Any website':   { site: '', match: '^https?:\\/\\/' },
  },
};

const form = $('Lead Intake Form').first().json;

function asList(value) {
  if (Array.isArray(value)) return value.map(String);
  const s = String(value ?? '').trim();
  if (!s) return [];
  try {
    const parsed = JSON.parse(s);
    if (Array.isArray(parsed)) return parsed.map(String);
  } catch (e) {}
  return s.split(',').map((x) => x.trim()).filter(Boolean);
}

const targetLeads = Number(form['Maximum leads']);
if (![10, 25, 50].includes(targetLeads)) {
  throw new Error(`Invalid Maximum leads value: ${form['Maximum leads']}`);
}

const mode = String(form.Mode || '').toLowerCase().includes('job') ? 'jobs' : 'clients';
const modeLabel = mode === 'jobs' ? 'Jobs' : 'Clients';

let boardNames = asList(form['Job boards']).filter((b) => CONFIG.boards[b]);
if (!boardNames.length) boardNames = ['LinkedIn Jobs', 'Rozee.pk', 'Indeed'];
const boards = boardNames.map((name) => ({ name, ...CONFIG.boards[name] }));

const tbsMap = {
  'Past 24 hours': 'qdr:d',
  'Past week': 'qdr:w',
  'Past month': 'qdr:m',
  'Any time': '',
};
const tbs = tbsMap[form['Posted within']] ?? 'qdr:w';

const minScore = Math.min(5, Math.max(1, Number(form['Minimum fit score (1-5)'] || 3)));
const rankingField = String(form['Ranking method'] || '').toLowerCase();
const rankingMode = rankingField.includes('no ranking') ? 'none'
  : rankingField.includes('keyword') ? 'keyword' : 'ai';
const rankingLabel = { ai: 'AI (Gemini)', keyword: 'Keyword', none: 'None' }[rankingMode];

const findContacts = mode === 'clients'
  && String(form['Find a decision-maker? (clients mode)'] || 'Yes').toLowerCase().startsWith('y');

const existingRows = $('Load Existing Leads').all()
  .filter((i) => i.json && String(i.json['Job URL'] || '').trim());

return [{
  json: {
    form,
    mode,
    modeLabel,
    config: {
      aiModel: CONFIG.aiModel,
      aiMinIntervalMs: CONFIG.aiMinIntervalMs,
      firecrawlDelayMs: CONFIG.firecrawlDelayMs,
      maxConsecutiveApiErrors: CONFIG.maxConsecutiveApiErrors,
      contactRoles: CONFIG.contactRoles,
      boards,
      tbs,
      minScore: rankingMode === 'none' ? 1 : minScore,
      findContacts,
      rankingMode,
      rankingLabel,
      useAi: rankingMode === 'ai',
    },
    targetLeads,
    newLeadsSaved: 0,
    lowFitCount: 0,
    duplicateCount: 0,
    notJobCount: 0,
    aiErrorCount: 0,
    consecutiveUnsuccessfulAttempts: 0,
    consecutiveApiErrors: 0,
    lastApiError: '',
    lastAiCallAt: 0,
    maxRetries: Math.max(40, targetLeads * 3),
    maxAttempts: targetLeads * 25,
    attemptIndex: 0,
    seenUrls: [],
    seenKeys: [],
    candidateQueue: [],
    existingLeadCount: existingRows.length,
    searchRunId: String($execution.id),
    startedAt: $now.toISO(),
    shouldContinue: true,
    lastOutcome: null,
    status: 'running',
    useQueue: false,
  },
}];
