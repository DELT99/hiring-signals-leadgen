// Evaluate Open
// Decides whether the scraped job page is still open.
//   Closed  -> 404/410, a "no longer accepting / expired / filled" message, or a redirect to a job list
//   Open    -> page loaded and none of the above
//   Unverified -> the page could not be fetched (the lead is kept; better a false positive than a lost lead)

const lead = $('Build Open Check').item.json;
const cfg = lead.config;
const resp = $input.first().json || {};
const out = { ...lead };
delete out.scrapeBody;

const closedRe = new RegExp((cfg.closedPhrases || []).map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') || '$^', 'i');

function parseAge(text) {
  const t = String(text || '');
  const m = t.match(/(\d+)\+?\s*(minute|min|hour|hr|day|week|wk|month|mo|year|yr)s?\s+ago/i);
  if (!m) return null;
  const n = Number(m[1]);
  const u = m[2].toLowerCase();
  const days = /^(minute|min|hour|hr)/.test(u) ? 0 : /^day/.test(u) ? n
    : /^(week|wk)/.test(u) ? n * 7 : /^(month|mo)/.test(u) ? n * 30 : n * 365;
  return { days, text: m[0] };
}

out.stillOpen = true;
out.pageChecked = true;
const data = resp.data || {};
const meta = data.metadata || {};
const status = Number(meta.statusCode || 0);
const md = String(data.markdown || '');

if (resp.success === false || resp.error || (!md && !status)) {
  out['Open Check'] = 'Unverified (page check failed)';
} else if (status === 404 || status === 410) {
  out.stillOpen = false;
  out['Open Check'] = `Closed (HTTP ${status})`;
} else {
  const finalUrl = String(meta.url || meta.sourceURL || '');
  const redirectedAway = finalUrl && (/[?&]error=true/i.test(finalUrl) ||
    (/greenhouse\.io|lever\.co/i.test(lead['Job URL']) && !/\/jobs?\/|lever\.co\/[^/]+\/[0-9a-f-]{8,}/i.test(finalUrl)));
  const head = md.slice(0, 4000);   // closed banners are near the top
  const closedMatch = head.match(closedRe);
  const age = parseAge(head);
  const maxAge = Number(cfg.maxAgeDays || 0);

  if (closedMatch) {
    out.stillOpen = false;
    out['Open Check'] = `Closed ("${closedMatch[0]}")`;
  } else if (redirectedAway) {
    out.stillOpen = false;
    out['Open Check'] = 'Closed (redirected to job list)';
  } else if (age && maxAge && age.days > maxAge) {
    out.stillOpen = false;
    out['Open Check'] = `Stale (${age.text})`;
  } else {
    out['Open Check'] = 'Open (page checked)';
  }
  if (age && !out['Posted']) out['Posted'] = age.text;
}

if (!out.stillOpen) out.outcome = 'closed';
return [{ json: out }];
