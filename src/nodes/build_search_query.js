// Build Search Query
// Uses queued results first; otherwise builds the next job-board query.
// Rotates boards and query patterns, then broadens when results dry up.

const state = $input.first().json;
const cfg = state.config;
const form = state.form;
const attempt = Number(state.attemptIndex || 0);
const consec = Number(state.consecutiveUnsuccessfulAttempts || 0);
const candidateQueue = Array.isArray(state.candidateQueue) ? state.candidateQueue : [];

// 1) Drain queued results before paying for another search
if (candidateQueue.length > 0) {
  return [{
    json: { ...state, useQueue: true, searchQuery: '[queue]', firecrawlBody: {}, candidateQueue },
  }];
}

// 2) Polite pacing (longer after an API error)
if (attempt > 0) {
  const base = Number(cfg.firecrawlDelayMs || 700);
  const delay = state.lastOutcome === 'api_error' ? 5000
    : consec >= 20 ? base * 2 : consec >= 10 ? base * 1.4 : base;
  await new Promise((resolve) => setTimeout(resolve, delay));
}

const role = String(form['Role or skill keywords'] || '').replace(/\s+/g, ' ').trim();
const location = String(form.Location || '').trim();

const roleParts = role.split(/\s*,\s*|\s+OR\s+/i).map((s) => s.trim()).filter(Boolean);
const locParts = location.split(/[\/,|]/).map((s) => s.trim()).filter(Boolean);
const isRemote = (s) => /remote|anywhere|worldwide/i.test(s);

function pick(arr, i) { return arr.length ? arr[i % arr.length] : ''; }
function quote(s) { return s ? `"${s}"` : ''; }

const boards = cfg.boards;
const board = boards[attempt % boards.length];
const round = Math.floor(attempt / boards.length);

const roleTerm = pick(roleParts, round) || role;
const roleOr = roleParts.length > 1 ? `(${roleParts.map(quote).join(' OR ')})` : quote(roleTerm);
const locTerm = pick(locParts, Math.floor(round / 2)) || location;
const locQ = isRemote(locTerm) ? 'remote' : quote(locTerm);
const locPlain = isRemote(locTerm) ? 'remote' : locTerm;

const sitePart = board.site ? `site:${board.site}` : '(hiring OR careers OR "job opening")';

const patterns = [
  () => `${sitePart} ${quote(roleTerm)} ${locQ}`,
  () => `${sitePart} ${roleOr} ${locQ}`,
  () => `${sitePart} intitle:${quote(roleTerm)} ${locPlain}`,
  () => `${sitePart} ${quote(roleTerm)} ${locPlain} hiring`,
  () => `${sitePart} ${roleOr} ${locPlain}`,
];

const clean = (q) => q.replace(/""/g, '').replace(/\s+/g, ' ').trim();
let query = clean(patterns[round % patterns.length]());

// Progressive broadening when stuck
if (consec >= 12) query = clean(`${sitePart} ${roleOr} ${locPlain}`);
if (consec >= 24) query = clean(`${sitePart} ${roleTerm} ${locParts[0] || ''}`);

let tbs = cfg.tbs;
if (consec >= 25 && tbs === 'qdr:d') tbs = 'qdr:w';
if (consec >= 35 && tbs === 'qdr:w') tbs = 'qdr:m';

const firecrawlBody = { query, limit: consec >= 15 ? 15 : 10 };
if (tbs) firecrawlBody.tbs = tbs;
if (locTerm && !isRemote(locTerm) && consec < 12 && attempt % 2 === 0) {
  firecrawlBody.location = locTerm;
}

return [{
  json: {
    ...state,
    useQueue: false,
    searchQuery: query,
    currentBoard: board.name,
    firecrawlBody,
    candidateQueue: [],
  },
}];
