// Parse AI Result
// Reads Gemini's JSON verdict, or classifies the error and decides:
//   retry (same or next model)  ->  aiRetry = true   (loops back to Build AI Prompt)
//   give up                     ->  falls back to the keyword score computed earlier
// Outcomes: qualified | low_fit | not_job | closed | duplicate

const lead = $('Build AI Prompt').item.json;
const cfg = lead.config;
const resp = $input.first().json || {};
const models = cfg.aiModels || [];

function dedupeSlug(s) {
  return String(s || '').toLowerCase()
    .replace(/\b(pvt|private|ltd|limited|inc|llc|co|company|corp)\b\.?/g, '')
    .replace(/[^a-z0-9]+/g, '');
}
function rowKey(row) {
  // Old sheets had a "Dedupe Key" column; new ones are keyed on Mode + Company + Job Title
  if (row['Dedupe Key']) return String(row['Dedupe Key']);
  const m = String(row.Mode || '').toLowerCase().startsWith('job') ? 'jobs' : 'clients';
  return row.Company && row['Job Title'] ? `${m}|${dedupeSlug(row.Company)}|${dedupeSlug(row['Job Title'])}` : '';
}
function routeFlags(o) {
  o.qualified = o.outcome === 'qualified';
  const skipDomain = (cfg.verifySkipDomains || []).find((d) => String(o['Job URL']).includes(d));
  o.needOpenCheck = o.qualified && cfg.verifyOpen && !skipDomain;
  if (o.qualified && cfg.verifyOpen && skipDomain) o['Open Check'] = `Snippet only (${skipDomain})`;
  o.needContact = o.qualified && cfg.findContacts && Boolean(o['Company']);
}

// ---- location matching ----
const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const hasTerm = (t, w) => new RegExp(`(^|[^a-z])${esc(w)}([^a-z]|$)`, 'i').test(t);
const groups = cfg.locationGroups || {};
function groupOf(name) {
  const k = name.toLowerCase();
  for (const [g, v] of Object.entries(groups)) {
    if (g === k || v.aliases.includes(k)) return { type: 'country', key: g, v };
    if (v.cities.includes(k)) return { type: 'city', key: g, v };
  }
  return null;
}
function termsFor(loc) {
  const k = loc.toLowerCase();
  if ((cfg.remoteAliases || []).includes(k) || /remote/.test(k)) return cfg.remoteAliases || ['remote'];
  const g = groupOf(k);
  if (g && g.type === 'country') return [...g.v.aliases, ...g.v.cities];
  return [k];
}
const selected = (cfg.locations || []).map((l) => ({ label: l, terms: termsFor(l) }));
// Countries that contain a selected city: "Pakistan" alone is not evidence of "another location"
const parentCountries = new Set(selected.map((s) => groupOf(s.label)).filter((g) => g && g.type === 'city')
  .flatMap((g) => g.v.aliases));
const selectedTerms = new Set(selected.flatMap((s) => s.terms));
const knownOther = [
  ...Object.values(groups).flatMap((v) => [...v.aliases, ...v.cities]),
  ...(cfg.otherKnownLocations || []),
].filter((a) => !selectedTerms.has(a) && !parentCountries.has(a));
// -> { status: 'match' | 'other' | 'unknown', loc }
function matchLocation(text) {
  const t = String(text || '').toLowerCase();
  if (!t.trim()) return { status: 'unknown' };
  for (const s of selected) if (s.terms.some((w) => hasTerm(t, w))) return { status: 'match', loc: s.label };
  const other = knownOther.find((w) => hasTerm(t, w));
  return other ? { status: 'other', loc: other } : { status: 'unknown' };
}

// ---------- parse ----------
let ai = null;
let errMsg = '';
let errCode = 0;
let retryDelayMs = 0;
try {
  const e = resp.error;
  if (e) {
    errCode = Number(e.code || e.httpCode || resp.statusCode || 0);
    errMsg = String(e.message || e.description || (typeof e === 'string' ? e : JSON.stringify(e)));
    const ri = (e.details || []).find((d) => d && d.retryDelay);
    if (ri) retryDelayMs = Math.min(60000, Math.round(parseFloat(ri.retryDelay) * 1000) || 0);
    throw new Error(errMsg);
  }
  const cand = resp.candidates?.[0];
  if (!cand) throw new Error(resp.promptFeedback?.blockReason ? `Blocked: ${resp.promptFeedback.blockReason}` : 'Empty Gemini response');
  const text = (cand.content?.parts || []).filter((p) => !p.thought).map((p) => p.text || '').join('').trim();
  if (!text) throw new Error(`No text (finishReason: ${cand.finishReason || 'unknown'})`);
  ai = JSON.parse(text.replace(/^```(?:json)?\s*|\s*```$/g, ''));
} catch (e) {
  errMsg = String(errMsg || e.message || e).slice(0, 200);
}

const out = { ...lead };
delete out.geminiBody;
out.aiRetry = false;
out.aiRetryDelayMs = 0;

if (!ai) {
  // ---------- classify the error ----------
  const m = errMsg.toLowerCase();
  const attempt = Number(lead.aiAttempt || 0) + 1;
  const idx = Number(lead.aiModelIdx || 0);
  const hasNextModel = idx + 1 < models.length;

  const isThinkingErr = errCode === 400 && /thinking/.test(m);
  const isNotFound = errCode === 404 || /not found|is not supported/.test(m);
  const isAuth = errCode === 401 || errCode === 403 || /api key not valid|permission|unauthenticated/.test(m);
  const isDaily = /per day|perday|daily/.test(m);
  const isRate = errCode === 429 || /resource_exhausted|quota|rate limit/.test(m);
  const isBusy = [500, 502, 503, 504].includes(errCode) ||
    /timeout|timed out|high demand|overloaded|unavailable|try again|econnreset|socket hang up/.test(m);

  let retry = false;
  let nextIdx = idx;
  if (attempt < Number(cfg.aiMaxAttemptsPerLead || 4) && !isAuth) {
    if (isThinkingErr) { retry = true; out.aiNoThinkingRun = true; }
    else if (isNotFound || isDaily) { retry = hasNextModel; nextIdx = idx + 1; }
    else if (isRate) { retry = true; out.aiRetryDelayMs = retryDelayMs || 15000; if (attempt >= 2 && hasNextModel) nextIdx = idx + 1; }
    else if (isBusy) { retry = true; if (attempt >= 2 && hasNextModel) nextIdx = idx + 1; }
    else { retry = attempt < 2; }  // unknown error (e.g. bad JSON): one more try
  }

  if (retry) {
    out.aiRetry = true;
    out.aiAttempt = attempt;
    out.aiModelIdx = nextIdx;
    // Remember a model switch for the rest of the run when the old model is unusable
    if (nextIdx !== idx && (isNotFound || isDaily)) out.aiModelIdxRun = nextIdx;
    out.lastAiError = errMsg;
    return [{ json: out }];
  }

  // ---------- give up: fall back to the keyword score ----------
  out.aiError = errMsg;
  out.lastAiError = errMsg;
  out.consecutiveAiFailures = Number(lead.consecutiveAiFailures || 0) + 1;
  if (isAuth || out.consecutiveAiFailures >= Number(cfg.aiDisableAfterFailures || 3)) out.aiDisabled = true;
  const score = Number(lead.keywordScore || 1);
  out['Fit Score'] = score;
  out['Fit Reason'] = `Keyword score (AI unavailable: ${errMsg.slice(0, 80)}): ${lead.keywordReason || ''}`;
  out.outcome = score < cfg.minScore ? 'low_fit' : 'qualified';
  routeFlags(out);
  return [{ json: out }];
}

// ---------- success ----------
out.aiError = '';
out.consecutiveAiFailures = 0;
out.aiModelIdxRun = Number(lead.aiModelIdx || 0);   // stick with the model that works
out['Company'] = String(ai.company || '').trim() || lead['Company'];
out['Job Title'] = String(ai.role || '').trim() || lead['Job Title'];
out['Location'] = String(ai.location || '').trim() || lead['Location'];
const score = Math.min(5, Math.max(1, Math.round(Number(ai.fit_score) || 1)));
out['Fit Score'] = score;
out['Fit Reason'] = String(ai.fit_reason || '').trim();
out['Angle / Tip'] = String(ai.angle || '').trim();

out['Dedupe Key'] = out['Company'] && out['Job Title']
  ? `${lead.mode}|${dedupeSlug(out['Company'])}|${dedupeSlug(out['Job Title'])}` : '';

const knownKeys = new Set(lead.seenKeys || []);
for (const row of $('Load Existing Leads').all()) {
  const k = row.json && rowKey(row.json);
  if (k) knownKeys.add(k);
}

const aiLoc = matchLocation(out['Location']);
if (aiLoc.status === 'match') out.matchedLocation = aiLoc.loc;

if (ai.is_job_posting === false) out.outcome = 'not_job';
else if (cfg.strictLocation && aiLoc.status === 'other') {
  out.outcome = 'wrong_location';
  out['Fit Reason'] = `Skipped: located in ${out['Location']}`;
}
else if (ai.is_open === false) { out.outcome = 'closed'; out['Open Check'] = 'Closed (AI read snippet)'; }
else if (out['Dedupe Key'] && knownKeys.has(out['Dedupe Key'])) out.outcome = 'duplicate';
else if (score < cfg.minScore) out.outcome = 'low_fit';
else out.outcome = 'qualified';

routeFlags(out);
return [{ json: out }];
