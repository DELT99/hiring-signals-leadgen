// Init Run State
// Reads the form, sets up configuration and the loop's state object.
// Edit CONFIG below to tune the workflow without touching other nodes.

const CONFIG = {
  // --- Gemini (AI ranking) ---
  // Tried in order. If a model is overloaded, timing out or out of quota, the next one is used.
  aiModels: ['gemini-3.5-flash-lite', 'gemini-3.5-flash', 'gemini-3.1-flash-lite'],
  aiThinkingLevel: 'minimal',       // minimal = fastest; scoring a job post needs no deep reasoning
  aiMinIntervalMs: 4500,            // minimum gap between Gemini calls (free-tier friendly)
  aiMaxAttemptsPerLead: 4,          // retries per posting (with backoff + model fallback)
  aiDisableAfterFailures: 3,        // after N postings in a row fail, switch the run to keyword scoring
  aiPrefilterMinScore: 2,           // only send postings with keyword score >= this to Gemini (saves quota)

  // --- Firecrawl ---
  firecrawlDelayMs: 700,            // pause between Firecrawl searches
  maxConsecutiveApiErrors: 3,       // stop the run if Firecrawl keeps failing

  // --- Closed / stale job filtering ---
  queryExclusions: ['"no longer accepting"', '"job has expired"'],
  closedPhrases: [
    'no longer accepting applications', 'no longer accepting', 'job is no longer available',
    'this job has expired', 'job has expired', 'job expired', 'position has been filled',
    'position is filled', 'applications are closed', 'applications closed', 'this job is closed',
    'job is closed', 'vacancy closed', 'not accepting applications', 'posting has closed',
    'this position is no longer', 'the job you are looking for', 'job not found',
  ],
  maxAgeDays: { 'qdr:d': 2, 'qdr:w': 10, 'qdr:m': 35, '': 0 },  // 0 = no age limit
  verifySkipDomains: ['linkedin.com'],   // page check is never run on these (snippet signals only)

  // --- Location matching (for the "Only keep jobs in my locations" filter) ---
  // Picking a country also accepts its cities; picking a city rejects jobs clearly in other cities.
  locationGroups: {
    pakistan: { aliases: ['pakistan'], cities: ['lahore', 'karachi', 'islamabad', 'rawalpindi', 'faisalabad', 'peshawar', 'multan', 'quetta', 'sialkot', 'gujranwala'] },
    uae: { aliases: ['uae', 'united arab emirates', 'emirates'], cities: ['dubai', 'abu dhabi', 'sharjah', 'ajman'] },
    'saudi arabia': { aliases: ['saudi arabia', 'saudi', 'ksa'], cities: ['riyadh', 'jeddah', 'dammam', 'khobar'] },
    qatar: { aliases: ['qatar'], cities: ['doha'] },
    bahrain: { aliases: ['bahrain'], cities: ['manama'] },
    oman: { aliases: ['oman'], cities: ['muscat'] },
    kuwait: { aliases: ['kuwait'], cities: [] },
  },
  remoteAliases: ['remote', 'work from home', 'wfh', 'anywhere', 'worldwide', 'fully remote'],
  otherKnownLocations: [
    'india', 'bangalore', 'bengaluru', 'delhi', 'mumbai', 'pune', 'chennai', 'noida', 'gurgaon',
    'london', 'united kingdom', 'uk', 'usa', 'united states', 'new york', 'san francisco', 'canada',
    'toronto', 'germany', 'berlin', 'netherlands', 'amsterdam', 'singapore', 'australia', 'sydney',
    'egypt', 'cairo', 'bangladesh', 'dhaka', 'turkey', 'istanbul', 'malaysia', 'philippines',
  ],

  // --- Decision-maker lookup ---
  contactRoles: [
    'CTO', '"Head of Engineering"', '"Engineering Manager"', 'Founder', 'CEO',
    '"Talent Acquisition"', '"HR Manager"',
  ],

  // Job boards: site filter for the query + regex a single posting URL must match.
  boards: {
    'LinkedIn Jobs': { site: 'linkedin.com/jobs/view', match: 'linkedin\\.com\\/jobs\\/view\\/' },
    // "reject" = listing / search-result pages on that board (not a single job)
    'Rozee.pk':      { site: 'rozee.pk', match: 'rozee\\.pk\\/', reject: '\\/job\\/jsearch|\\/jobs-in-|\\/search|\\/compan(y|ies)\\/[^/]*$|[?&]q=' },
    'Indeed':        { site: 'indeed.com', match: 'indeed\\.com\\/(viewjob|rc\\/clk|m\\/viewjob|m\\/basecamp\\/viewjob)|indeed\\.com\\/.*[?&]jk=' },
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
const yes = (v, dflt) => String(v ?? dflt).toLowerCase().startsWith('y');

// Roles and locations: multi-select dropdown + free-text "Other ..." box (comma-separated).
// Older forms with single text fields still work.
// Roles split on , ; | (not "/", so "UI/UX Designer" survives); locations also split on "/".
const splitList = (v, slash = false) => asList(v).flatMap((x) => String(x).split(slash ? /\s*[,;\/|]\s*/ : /\s*[,;|]\s*|\s+OR\s+/i))
  .map((x) => x.replace(/\s*\(anywhere\)\s*$/i, '').replace(/\s+/g, ' ').trim()).filter(Boolean);
const uniqCI = (arr) => arr.filter((x, i) => arr.findIndex((y) => y.toLowerCase() === x.toLowerCase()) === i);
const roles = uniqCI([
  ...asList(form['Roles']),
  ...splitList(form['Other roles (comma-separated)']),
  ...splitList(form['Role or skill keywords']),
].map((x) => String(x).trim()).filter(Boolean));
const locations = uniqCI([
  ...asList(form['Locations']).map((x) => x.replace(/\s*\(anywhere\)\s*$/i, '')),
  ...splitList(form['Other locations (comma-separated)'], true),
  ...splitList(form['Location'], true),
].map((x) => String(x).trim()).filter(Boolean));
if (!roles.length) throw new Error('Pick at least one role (or type one in "Other roles").');
if (!locations.length) throw new Error('Pick at least one location (or type one in "Other locations").');
const strictLocation = !String(form['Location filter'] || 'Only').toLowerCase().startsWith('keep all');

const targetLeads = Number(form['Maximum leads']);
if (![10, 25, 50].includes(targetLeads)) {
  throw new Error(`Invalid Maximum leads value: ${form['Maximum leads']}`);
}

const mode = String(form.Mode || '').toLowerCase().includes('job') ? 'jobs' : 'clients';
const modeLabel = mode === 'jobs' ? 'Jobs' : 'Clients';

let boardNames = asList(form['Job boards']).filter((b) => CONFIG.boards[b]);
if (!boardNames.length) boardNames = ['LinkedIn Jobs', 'Rozee.pk', 'Indeed'];
const boards = boardNames.map((name) => ({ name, ...CONFIG.boards[name] }));

const tbsMap = { 'Past 24 hours': 'qdr:d', 'Past week': 'qdr:w', 'Past month': 'qdr:m', 'Any time': '' };
const tbs = tbsMap[form['Posted within']] ?? 'qdr:w';

const rankingField = String(form['Ranking method'] || '').toLowerCase();
const rankingMode = rankingField.includes('no ranking') ? 'none'
  : rankingField.includes('keyword') ? 'keyword' : 'ai';
const rankingLabel = { ai: 'AI (Gemini)', keyword: 'Keyword', none: 'None' }[rankingMode];

const minScore = Math.min(5, Math.max(1, Number(form['Minimum fit score (1-5)'] || 3)));
const findContacts = mode === 'clients' && yes(form['Find a decision-maker? (clients mode)'], 'Yes');
const verifyOpen = yes(form['Check job is still open? (extra credits)'], 'Yes');

const existingRows = $('Load Existing Leads').all()
  .filter((i) => i.json && String(i.json['Job URL'] || '').trim());

return [{
  json: {
    form,
    mode,
    modeLabel,
    config: {
      aiModels: CONFIG.aiModels,
      aiThinkingLevel: CONFIG.aiThinkingLevel,
      aiMinIntervalMs: CONFIG.aiMinIntervalMs,
      aiMaxAttemptsPerLead: CONFIG.aiMaxAttemptsPerLead,
      aiDisableAfterFailures: CONFIG.aiDisableAfterFailures,
      aiPrefilterMinScore: CONFIG.aiPrefilterMinScore,
      firecrawlDelayMs: CONFIG.firecrawlDelayMs,
      maxConsecutiveApiErrors: CONFIG.maxConsecutiveApiErrors,
      queryExclusions: CONFIG.queryExclusions,
      closedPhrases: CONFIG.closedPhrases,
      maxAgeDays: CONFIG.maxAgeDays[tbs] ?? 0,
      verifySkipDomains: CONFIG.verifySkipDomains,
      contactRoles: CONFIG.contactRoles,
      roles,
      locations,
      rolesText: roles.join(', '),
      locationsText: locations.join(', '),
      strictLocation,
      locationGroups: CONFIG.locationGroups,
      remoteAliases: CONFIG.remoteAliases,
      otherKnownLocations: CONFIG.otherKnownLocations,
      boards,
      tbs,
      minScore: rankingMode === 'none' ? 1 : minScore,
      findContacts,
      verifyOpen,
      rankingMode,
      rankingLabel,
      useAi: rankingMode === 'ai',
    },
    targetLeads,
    newLeadsSaved: 0,
    lowFitCount: 0,
    duplicateCount: 0,
    notJobCount: 0,
    closedCount: 0,
    wrongLocationCount: 0,
    aiErrorCount: 0,
    aiFallbackCount: 0,
    consecutiveAiFailures: 0,
    aiDisabled: false,
    aiModelIdxRun: 0,
    aiNoThinkingRun: false,
    consecutiveUnsuccessfulAttempts: 0,
    consecutiveApiErrors: 0,
    lastApiError: '',
    lastAiError: '',
    lastAiCallAt: 0,
    maxRetries: Math.max(40, targetLeads * 3),
    maxAttempts: targetLeads * 25,
    attemptIndex: 0,
    savedByBoard: {},
    missesByBoard: {},
    boardSearchIdx: {},
    pageCheckedCount: 0,
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
