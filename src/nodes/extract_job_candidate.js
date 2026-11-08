// Extract Job Candidate
// Turns Firecrawl search results into one job candidate (and queues the rest).
// Skips listing/search pages, non-posting URLs, closed or stale postings and anything already seen.

const state = $('Build Search Query').item.json;
const cfg = state.config;
const form = state.form;

const boards = cfg.boards.map((b) => ({ ...b, re: new RegExp(b.match, 'i'), rejectRe: b.reject ? new RegExp(b.reject, 'i') : null }));
const MAX_QUEUE = 60;
const excludedDomains = ['youtube.com', 'wikipedia.org', 'facebook.com', 'instagram.com', 'reddit.com'];
const listingTitle = [
  /\b\d[\d,]*\+?\s+.*\bjobs?\b/i,              // "120 Flutter Developer jobs in Lahore"
  /\bjobs?\s*(in|near)\b.*\(with salaries\)/i,
  /\b(vacancies|job openings|jobs and careers)\b/i,
  /^jobs?\s+(in|for)\b/i,
];

const closedRe = new RegExp((cfg.closedPhrases || []).map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') || '$^', 'i');

// "3 days ago", "30+ days ago", "2 weeks ago", "yesterday", "Posted on Oct 12, 2026" -> age in days
function parseAge(text) {
  const t = String(text || '');
  let m = t.match(/(\d+)\+?\s*(minute|min|hour|hr|day|week|wk|month|mo|year|yr)s?\s+ago/i);
  if (m) {
    const n = Number(m[1]);
    const unit = m[2].toLowerCase();
    const days = /^(minute|min|hour|hr)/.test(unit) ? 0 : /^(day)/.test(unit) ? n
      : /^(week|wk)/.test(unit) ? n * 7 : /^(month|mo)/.test(unit) ? n * 30 : n * 365;
    return { days, text: m[0] };
  }
  if ((m = t.match(/\b(just now|today|just posted|new)\b/i))) return { days: 0, text: m[0] };
  if ((m = t.match(/\byesterday\b/i))) return { days: 1, text: m[0] };
  m = t.match(/\b(?:posted|published|date posted)[:\s]*(?:on\s+)?([A-Z][a-z]{2,8}\.? \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2})/i);
  if (m) {
    const d = Date.parse(m[1].replace('.', ''));
    if (!Number.isNaN(d)) return { days: Math.max(0, Math.floor((Date.now() - d) / 86400000)), text: m[1] };
  }
  return null;
}

function normalizeJobUrl(raw) {
  const s = String(raw || '').trim();
  if (!s) return '';
  let u;
  try { u = new URL(s); } catch (e) { return s.toLowerCase().replace(/[?#].*$/, '').replace(/\/+$/, ''); }
  const host = u.hostname.toLowerCase().replace(/^www\./, '');
  if (/(^|\.)linkedin\.com$/.test(host)) {
    const m = u.pathname.match(/\/jobs\/view\/(?:[^/]*?-)?(\d{6,})/);
    if (m) return `https://www.linkedin.com/jobs/view/${m[1]}`;
  }
  if (/(^|\.)indeed\.com$/.test(host)) {
    const jk = u.searchParams.get('jk') || u.searchParams.get('vjk');
    if (jk) return `https://www.indeed.com/viewjob?jk=${jk}`;
  }
  const path = u.pathname.replace(/\/+$/, '');
  return `https://${host}${path}`.toLowerCase();
}

function dedupeSlug(s) {
  return String(s || '').toLowerCase()
    .replace(/\b(pvt|private|ltd|limited|inc|llc|co|company|corp)\b\.?/g, '')
    .replace(/[^a-z0-9]+/g, '');
}

// Seen = URLs handled this run + URLs already in the sheet for this mode
const seen = new Set(state.seenUrls || []);
for (const row of $('Load Existing Leads').all()) {
  const j = row.json || {};
  if (String(j.Mode || '') !== state.modeLabel) continue;
  const u = normalizeJobUrl(j['Job URL']);
  if (u) seen.add(u);
}

function boardFor(url) {
  // Most specific board first; "Any website" last
  const specific = boards.filter((b) => b.site);
  for (const b of specific) {
    if (b.re.test(url)) return b.rejectRe && b.rejectRe.test(url) ? '' : b.name;   // reject = listing/search pages
  }
  const any = boards.find((b) => !b.site);
  return any && any.re.test(url) ? any.name : '';
}

// Heuristic title parse; Gemini refines these later
function parseTitle(title, url) {
  let t = String(title || '').replace(/\s+/g, ' ').trim()
    .replace(/\s*[|\-–—]\s*(LinkedIn|Indeed(\.com)?|Rozee\.pk|Bayt\.com|Greenhouse|Lever)\s*$/i, '')
    .replace(/\s*(\.\.\.|…)\s*$/, '');
  let company = '';
  let role = '';
  let loc = '';
  let m;
  if ((m = t.match(/^(.+?) hiring (.+?) in (.+)$/i))) { [, company, role, loc] = m; }
  else if ((m = t.match(/^Job Application for (.+?) at (.+)$/i))) { [, role, company] = m; }
  else if ((m = t.match(/^(.+?) jobs? in (.+?) at (.+)$/i))) { [, role, loc, company] = m; }
  else {
    const parts = t.split(/\s+[|\-–—]\s+/).map((s) => s.trim()).filter(Boolean);
    if (/jobs\.lever\.co/i.test(url)) { [company = '', role = ''] = parts; }
    else { [role = '', company = '', loc = ''] = parts; }
  }
  if (!company) {
    const gh = url.match(/greenhouse\.io\/([^/]+)\/jobs/i) || url.match(/jobs\.lever\.co\/([^/]+)/i);
    if (gh) company = gh[1].replace(/[-_]+/g, ' ');
  }
  return { company: company.trim(), role: role.trim(), loc: loc.trim() };
}

function basePayload(extra = {}) {
  return {
    ...state,
    hasCandidate: false,
    outcome: 'empty',
    normalizedUrl: '',
    apiError: '',
    'Date Added': $now.toISODate(),
    'Time Added': $now.toFormat('HH:mm:ss'),
    'Mode': state.modeLabel,
    'Company': '',
    'Job Title': '',
    'Location': '',
    'Job Board': '',
    'Job URL': '',
    'Snippet': '',
    'Fit Score': '',
    'Fit Reason': '',
    'Angle / Tip': '',
    'Contact Name': '',
    'Contact Title': '',
    'Contact LinkedIn': '',
    'Search Keywords': cfg.rolesText || '',
    'Run By': form['Your name'] ?? '',
    'Search Run ID': state.searchRunId,
    'Status': state.mode === 'jobs' ? 'To apply' : 'New',
    'Dedupe Key': '',
    'Posted': '',
    'Open Check': 'Not checked',
    closedFiltered: 0,
    ageDays: null,
    candidateQueue: Array.isArray(state.candidateQueue) ? state.candidateQueue : [],
    ...extra,
  };
}

function toCandidate(r, queue) {
  const p = parseTitle(r.title, r.url);
  const key = p.company && p.role
    ? `${state.mode}|${dedupeSlug(p.company)}|${dedupeSlug(p.role)}` : '';
  return basePayload({
    hasCandidate: true,
    outcome: 'candidate',
    normalizedUrl: r.normalizedUrl,
    'Company': p.company,
    'Job Title': p.role,
    'Location': p.loc,
    'Job Board': r.board,
    'Job URL': r.normalizedUrl,
    'Snippet': String(r.description || '').slice(0, 500),
    'Dedupe Key': key,
    'Posted': r.postedText || '',
    ageDays: r.ageDays ?? null,
    rawTitle: r.title,
    candidateQueue: queue,
  });
}

// A) Use a queued result
if (state.useQueue && state.candidateQueue && state.candidateQueue.length) {
  const i = Math.min(Number(state.queuePickIndex || 0), state.candidateQueue.length - 1);
  const next = state.candidateQueue[i];
  const rest = state.candidateQueue.filter((_, j) => j !== i);
  if (next.normalizedUrl && !seen.has(next.normalizedUrl)) {
    return [{ json: toCandidate(next, rest) }];
  }
  return [{ json: basePayload({ outcome: 'seen', candidateQueue: rest }) }];
}

// B) Parse the Firecrawl response
let response = {};
try { response = $('Firecrawl Search').item.json; } catch (e) { response = $input.first().json; }

if (!response || response.success === false || (response.error && !response.data)) {
  const msg = response && (response.error?.message || response.error || response.message);
  return [{ json: basePayload({ outcome: 'api_error', apiError: String(msg || 'Firecrawl request failed') }) }];
}

let results = [];
if (Array.isArray(response?.data?.web)) results = response.data.web;
else if (Array.isArray(response?.data)) results = response.data;
else if (Array.isArray(response?.web)) results = response.web;

if (!results.length) return [{ json: basePayload({ outcome: 'empty' }) }];

const usable = [];
const batch = new Set();
const existingQueue = Array.isArray(state.candidateQueue) ? state.candidateQueue : [];
const queuedUrls = new Set(existingQueue.map((q) => q.normalizedUrl));
let sawSeen = false;
let sawClosed = false;
let closedN = 0;
const maxAge = Number(cfg.maxAgeDays || 0);
for (const r of results) {
  const url = String(r.url ?? r.link ?? '').trim();
  const title = String(r.title ?? '').trim();
  const description = String(r.description ?? r.snippet ?? '').trim();
  if (!url || !title) continue;
  if (excludedDomains.some((d) => url.toLowerCase().includes(d))) continue;
  if (listingTitle.some((re) => re.test(title))) continue;
  const board = boardFor(url);
  if (!board) continue;
  const normalizedUrl = normalizeJobUrl(url);
  if (!normalizedUrl) continue;
  if (seen.has(normalizedUrl)) { sawSeen = true; continue; }
  if (batch.has(normalizedUrl) || queuedUrls.has(normalizedUrl)) continue;
  // Closed postings ("No longer accepting applications", "expired", ...)
  if (closedRe.test(`${title} ${description}`)) { sawClosed = true; closedN++; continue; }
  // Stale postings: snippet says it's older than the "Posted within" window
  const age = parseAge(description) || parseAge(title);
  if (age && maxAge && age.days > maxAge) { sawClosed = true; closedN++; continue; }
  batch.add(normalizedUrl);
  usable.push({ url, title, description, normalizedUrl, board, postedText: age ? age.text : '', ageDays: age ? age.days : null });
}

if (!usable.length) {
  return [{ json: basePayload({ outcome: sawClosed ? 'closed' : sawSeen ? 'seen' : 'invalid', closedFiltered: closedN }) }];
}

// New results join the queue (results from other boards stay in it); oldest dropped past MAX_QUEUE
const queue = [...existingQueue, ...usable.slice(1)].slice(-MAX_QUEUE);
return [{ json: { ...toCandidate(usable[0], queue), closedFiltered: closedN } }];
