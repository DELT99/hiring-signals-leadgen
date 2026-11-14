// Build Search Query
// Decides the next step of the loop, keeping leads balanced across the selected job boards:
//   1. The board with the fewest saved leads is always served next.
//   2. Each board gets a fair share of the target (target / boards). A board that reaches
//      its share is paused, so the others get a turn.
//   3. A board whose last DRY_AFTER results all failed (nothing found, duplicate, closed,
//      low fit, wrong location...) is marked "dry" and the remaining boards fill its share.
//      If every board is dry, all are tried again.
//   4. That board's queued results are used first (cheaper than a new search); if it has
//      none queued, it is searched.
// Each board cycles through every role x location combination on its own.

const state = $input.first().json;
const cfg = state.config;
const attempt = Number(state.attemptIndex || 0);
const consec = Number(state.consecutiveUnsuccessfulAttempts || 0);
const candidateQueue = Array.isArray(state.candidateQueue) ? state.candidateQueue : [];

const boards = cfg.boards;
const B = boards.length;
const DRY_AFTER = 6;                                    // failed results in a row before a board is "dry"
const share = Math.ceil(Number(state.targetLeads) / B);
const saved = state.savedByBoard || {};
const empty = state.missesByBoard || {};
const searches = state.boardSearchIdx || {};

const wet = boards.filter((b) => (empty[b.name] || 0) < DRY_AFTER);
let pool = wet.filter((b) => (saved[b.name] || 0) < share);
if (!pool.length) pool = wet;                           // others are dry: let the rest fill the target
let resetEmpty = false;
if (!pool.length) { pool = boards; resetEmpty = true; } // every board dry: give them all another go
const eligible = new Set(pool.map((b) => b.name));

// 1) Serve the neediest board (fewest saved leads). Use its queued results if it has any
//    (cheaper than a new search); otherwise search it.
const minSaved = Math.min(...pool.map((b) => saved[b.name] || 0));
const neediest = pool.filter((b) => (saved[b.name] || 0) === minSaved);
const needySet = new Set(neediest.map((b) => b.name));
const pickIdx = candidateQueue.findIndex((c) => needySet.has(c.board));
if (pickIdx >= 0) {
  return [{
    json: { ...state, useQueue: true, queuePickIndex: pickIdx, searchQuery: '[queue]', firecrawlBody: {},
      currentBoard: candidateQueue[pickIdx].board, resetEmpty },
  }];
}

// 2) Polite pacing (longer after an API error)
if (attempt > 0) {
  const base = Number(cfg.firecrawlDelayMs || 700);
  const delay = state.lastOutcome === 'api_error' ? 5000
    : consec >= 20 ? base * 2 : consec >= 10 ? base * 1.4 : base;
  await new Promise((resolve) => setTimeout(resolve, delay));
}

// 3) Search the neediest board (ties: the one searched least)
const board = neediest.slice().sort((a, b) => (searches[a.name] || 0) - (searches[b.name] || 0))[0];
const bIdx = searches[board.name] || 0;

const roles = cfg.roles && cfg.roles.length ? cfg.roles : ['developer'];
const locations = cfg.locations && cfg.locations.length ? cfg.locations : [''];
const isRemote = (s) => /remote|work from home/i.test(s);
const isAnywhere = (s) => !s || (cfg.anywhereAliases || ['anywhere']).includes(String(s).toLowerCase());
function quote(s) { return s ? `"${s}"` : ''; }

// This board's next role x location combination, then the next query pattern
const combos = [];
for (const r of roles) for (const l of locations) combos.push([r, l]);
const C = combos.length;
const [roleTerm, locTerm] = combos[bIdx % C];
const round = Math.floor(bIdx / C);

const roleOr = roles.length > 1 ? `(${roles.map(quote).join(' OR ')})` : quote(roleTerm);
const locQ = isAnywhere(locTerm) ? '' : isRemote(locTerm) ? 'remote' : quote(locTerm);
const locPlain = isAnywhere(locTerm) ? '' : isRemote(locTerm) ? 'remote' : locTerm;

const sitePart = board.site ? `site:${board.site}` : '(hiring OR careers OR "job opening")';

const patterns = [
  () => `${sitePart} ${quote(roleTerm)} ${locQ}`,
  () => `${sitePart} intitle:${quote(roleTerm)} ${locPlain}`,
  () => `${sitePart} ${quote(roleTerm)} ${locPlain} hiring`,
  () => `${sitePart} ${roleTerm} ${locPlain}`,
];

const clean = (q) => q.replace(/""/g, '').replace(/\s+/g, ' ').trim();
let query = clean(patterns[round % patterns.length]());

// Progressive broadening when stuck (location is always kept)
if (consec >= 12) query = clean(`${sitePart} ${roleOr} ${locPlain}`);
if (consec >= 24) query = clean(`${sitePart} ${roleTerm} ${locPlain}`);

// Exclude postings Google already shows as closed (e.g. LinkedIn "No longer accepting applications")
const exclusions = (cfg.queryExclusions || []).map((p) => `-${p}`).join(' ');
if (exclusions && consec < 30) query = clean(`${query} ${exclusions}`);

let tbs = cfg.tbs;
if (consec >= 25 && tbs === 'qdr:d') tbs = 'qdr:w';
if (consec >= 35 && tbs === 'qdr:w') tbs = 'qdr:m';

const firecrawlBody = { query, limit: consec >= 15 ? 15 : 10 };
if (tbs) firecrawlBody.tbs = tbs;
if (locTerm && !isRemote(locTerm) && !isAnywhere(locTerm) && consec < 12 && bIdx % 2 === 0) {
  firecrawlBody.location = locTerm;
}

return [{
  json: {
    ...state,
    useQueue: false,
    searchQuery: query,
    boardSearchIdx: { ...searches, [board.name]: bIdx + 1 },
    resetEmpty,
    currentBoard: board.name,
    currentCombo: `${roleTerm} @ ${locTerm || 'any'}`,
    firecrawlBody,
    candidateQueue,          // kept: queued results from other boards stay available
  },
}];
