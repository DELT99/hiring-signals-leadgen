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
let closedCount = Number(c.closedCount || 0);
let wrongLocationCount = Number(c.wrongLocationCount || 0);
let pageCheckedCount = Number(c.pageCheckedCount || 0) + (c.pageChecked ? 1 : 0);

// Per-board balance tracking (see Build Search Query)
const savedByBoard = { ...(c.savedByBoard || {}) };
const missesByBoard = c.resetEmpty ? {} : { ...(c.missesByBoard || {}) };
if (outcome === 'created' && c['Job Board']) savedByBoard[c['Job Board']] = (savedByBoard[c['Job Board']] || 0) + 1;
// Every pass is attributed to a board (the one searched, or the queued result's board).
// Misses in a row = results from that board that were not saved; a save resets it.
const passBoard = c['Job Board'] || c.currentBoard;
if (passBoard) missesByBoard[passBoard] = outcome === 'created' ? 0 : (missesByBoard[passBoard] || 0) + 1;
let aiFallbackCount = Number(c.aiFallbackCount || 0);
let consecutiveUnsuccessfulAttempts = Number(c.consecutiveUnsuccessfulAttempts || 0);
let consecutiveApiErrors = Number(c.consecutiveApiErrors || 0);
let lastApiError = c.lastApiError || '';
const attemptIndex = Number(c.attemptIndex || 0) + 1;

const seenUrls = Array.isArray(c.seenUrls) ? [...c.seenUrls] : [];
const seenKeys = Array.isArray(c.seenKeys) ? [...c.seenKeys] : [];
if (c.normalizedUrl && !seenUrls.includes(c.normalizedUrl)) seenUrls.push(c.normalizedUrl);
const key = c['Dedupe Key'];
if (key && ['created', 'low_fit', 'not_job', 'duplicate', 'closed', 'wrong_location'].includes(outcome) && !seenKeys.includes(key)) {
  seenKeys.push(key);
}

if (outcome === 'created') { newLeadsSaved += 1; consecutiveUnsuccessfulAttempts = 0; }
else consecutiveUnsuccessfulAttempts += 1;

if (outcome === 'low_fit') lowFitCount += 1;
if (outcome === 'duplicate') duplicateCount += 1;
if (outcome === 'not_job') notJobCount += 1;
if (outcome === 'wrong_location') wrongLocationCount += 1;
closedCount += Number(c.closedFiltered || 0);
if (outcome === 'closed' && !c.closedFiltered) closedCount += 1;
if (c.aiError) { aiErrorCount += 1; aiFallbackCount += 1; }

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
    aiFallbackCount,
    closedCount,
    wrongLocationCount,
    consecutiveAiFailures: Number(c.consecutiveAiFailures || 0),
    aiDisabled: Boolean(c.aiDisabled),
    aiModelIdxRun: Number(c.aiModelIdxRun || 0),
    aiNoThinkingRun: Boolean(c.aiNoThinkingRun),
    lastAiError: c.lastAiError || '',
    consecutiveUnsuccessfulAttempts,
    consecutiveApiErrors,
    lastApiError,
    lastAiCallAt: c.lastAiCallAt || 0,
    maxRetries: c.maxRetries,
    maxAttempts: c.maxAttempts,
    attemptIndex,
    savedByBoard,
    missesByBoard,
    boardSearchIdx: c.boardSearchIdx || {},
    pageCheckedCount,
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
