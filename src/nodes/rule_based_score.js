// Rule-Based Score
// Runs for EVERY candidate, before any AI call:
//   - computes a free keyword score (also the fallback if Gemini fails later)
//   - catches duplicates early so they never cost an AI call
//   - decides the outcome for Keyword / No-ranking modes
//   - in AI mode, sends only promising postings (keyword score >= aiPrefilterMinScore) to Gemini

const lead = $input.first().json;
const cfg = lead.config;
const form = lead.form;
const out = { ...lead };

const STOP = new Set(('and the for with from that this are you your our will have has who into able ' +
  'years year experience work working team teams strong good great skills skill job role looking ' +
  'want based plus etc also using use well can all any new more other per about over' +
  ' developer engineer senior junior lead').split(/\s+/));
const words = (s) => String(s || '').toLowerCase().split(/[^a-z0-9+#.]+/)
  .map((w) => w.replace(/\.+$/, '')).filter((w) => w.length >= 3 && !STOP.has(w));

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
const anywhere = (cfg.locations || []).some((l) => (cfg.anywhereAliases || []).includes(l.toLowerCase()));
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
  if (anywhere) return { status: 'match', loc: 'Anywhere' };
  const t = String(text || '').toLowerCase();
  if (!t.trim()) return { status: 'unknown' };
  for (const s of selected) if (s.terms.some((w) => hasTerm(t, w))) return { status: 'match', loc: s.label };
  const other = knownOther.find((w) => hasTerm(t, w));
  return other ? { status: 'other', loc: other } : { status: 'unknown' };
}

// ---- keyword score (always computed) ----
const title = String(lead.rawTitle || lead['Job Title'] || '').toLowerCase();
const text = `${title} ${String(lead.Snippet || '').toLowerCase()}`;

const rolePhrases = (cfg.roles || []).map((r) => r.toLowerCase());
let rolePts = 0;
let roleNote = 'no role match';
if (rolePhrases.some((p) => title.includes(p))) { rolePts = 2; roleNote = 'role matches title'; }
else if (rolePhrases.some((p) => words(p).some((w) => title.includes(w)))) { rolePts = 1; roleNote = 'role partly matches'; }

const locWords = new Set(selected.flatMap((s) => s.terms.flatMap((t) => words(t))));
const offerTerms = [...new Set(words(form['What you offer / your CV summary']))].filter((t) => !locWords.has(t));
const hits = offerTerms.filter((t) => text.includes(t));
const skillPts = hits.length >= 3 ? 2 : hits.length >= 1 ? 1 : 0;

const locMatch = matchLocation(`${lead.Location || ''} ${text}`);
const locPts = locMatch.status === 'match' ? 1 : 0;
out.matchedLocation = locMatch.status === 'match' ? locMatch.loc : '';

const keywordScore = Math.min(5, 1 + rolePts + skillPts + locPts);
const keywordReason = `${roleNote}; ${hits.length} skill match(es)` +
  (hits.length ? ` (${hits.slice(0, 5).join(', ')})` : '') + (locPts ? `; location matches (${locMatch.loc})` : '');
out.keywordScore = keywordScore;
out.keywordReason = keywordReason;

// ---- early duplicate check (company + role from the title) ----
const knownKeys = new Set(lead.seenKeys || []);
for (const row of $('Load Existing Leads').all()) {
  const k = row.json && rowKey(row.json);
  if (k) knownKeys.add(k);
}
const isDuplicate = Boolean(out['Dedupe Key']) && knownKeys.has(out['Dedupe Key']);

// ---- decide ----
out.sendToAi = false;
if (isDuplicate) {
  out.outcome = 'duplicate';
} else if (cfg.strictLocation && locMatch.status === 'other') {
  out.outcome = 'wrong_location';      // clearly in a location you didn't pick: skip, no AI call
  out['Fit Reason'] = `Skipped: located in ${locMatch.loc}`;
} else if (cfg.rankingMode === 'none') {
  out['Fit Score'] = '';
  out['Fit Reason'] = 'Not ranked';
  out.outcome = 'qualified';
} else if (cfg.useAi && !lead.aiDisabled && keywordScore >= Number(cfg.aiPrefilterMinScore || 1)) {
  out.sendToAi = true;          // Gemini decides
  out.outcome = 'pending_ai';
} else {
  out['Fit Score'] = keywordScore;
  const prefix = cfg.useAi
    ? (lead.aiDisabled ? 'Keyword score (AI paused for this run)' : 'Keyword score (below AI pre-filter)')
    : 'Keyword score';
  out['Fit Reason'] = `${prefix}: ${keywordReason}`;
  out.outcome = keywordScore < cfg.minScore ? 'low_fit' : 'qualified';
}

out.aiAttempt = 0;
routeFlags(out);
return [{ json: out }];
