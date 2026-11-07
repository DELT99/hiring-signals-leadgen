// Update Counters
// Records the outcome of this pass and decides whether the loop continues.

const c = $input.first().json;
const cfg = c.config;
const outcome = c.outcome || 'invalid';

let newLeadsSaved = Number(c.newLeadsSaved || 0);
let lowFitCount = Number(c.lowFitCount || 0);
let duplicateCount = Number(c.duplicateCount || 0);
let notJobCount = Number(c.notJobCount || 0);
let aiErrorCount = Number(c.aiErrorCount || 0);
let consecutiveUnsuccessfulAttempts = Number(c.consecutiveUnsuccessfulAttempts || 0);
let consecutiveApiErrors = Number(c.consecutiveApiErrors || 0);
let lastApiError = c.lastApiError || '';
const attemptIndex = Number(c.attemptIndex || 0) + 1;

const seenUrls = Array.isArray(c.seenUrls) ? [...c.seenUrls] : [];
const seenKeys = Array.isArray(c.seenKeys) ? [...c.seenKeys] : [];
if (c.normalizedUrl && !seenUrls.includes(c.normalizedUrl)) seenUrls.push(c.normalizedUrl);
const key = c['Dedupe Key'];
if (key && ['created', 'low_fit', 'not_job', 'duplicate'].includes(outcome) && !seenKeys.includes(key)) {
  seenKeys.push(key);
}

if (outcome === 'created') { newLeadsSaved += 1; consecutiveUnsuccessfulAttempts = 0; }
else consecutiveUnsuccessfulAttempts += 1;

if (outcome === 'low_fit') lowFitCount += 1;
if (outcome === 'duplicate') duplicateCount += 1;
if (outcome === 'not_job') notJobCount += 1;
if (c.aiError) aiErrorCount += 1;

if (outcome === 'api_error') { consecutiveApiErrors += 1; lastApiError = c.apiError || lastApiError; }
else consecutiveApiErrors = 0;

const maxApi = Number(cfg.maxConsecutiveApiErrors || 3);
const shouldContinue =
  newLeadsSaved < c.targetLeads &&
  consecutiveUnsuccessfulAttempts < c.maxRetries &&
  consecutiveApiErrors < maxApi &&
  attemptIndex < c.maxAttempts;

let status = 'running';
if (newLeadsSaved >= c.targetLeads) status = 'target_reached';
else if (consecutiveApiErrors >= maxApi) status = 'api_error';
else if (consecutiveUnsuccessfulAttempts >= c.maxRetries) status = 'retry_limit_reached';
else if (attemptIndex >= c.maxAttempts) status = 'max_attempts_reached';

return [{
  json: {
    form: c.form,
    mode: c.mode,
    modeLabel: c.modeLabel,
    config: cfg,
    targetLeads: c.targetLeads,
    newLeadsSaved,
    lowFitCount,
    duplicateCount,
    notJobCount,
    aiErrorCount,
    consecutiveUnsuccessfulAttempts,
    consecutiveApiErrors,
    lastApiError,
    lastAiCallAt: c.lastAiCallAt || 0,
    maxRetries: c.maxRetries,
    maxAttempts: c.maxAttempts,
    attemptIndex,
    seenUrls,
    seenKeys,
    candidateQueue: Array.isArray(c.candidateQueue) ? c.candidateQueue : [],
    existingLeadCount: c.existingLeadCount,
    searchRunId: c.searchRunId,
    startedAt: c.startedAt,
    shouldContinue,
    lastOutcome: outcome,
    status,
    useQueue: false,
  },
}];
