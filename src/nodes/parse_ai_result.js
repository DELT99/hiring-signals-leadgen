// Parse AI Result
// Reads Gemini's JSON verdict, merges it into the lead, and decides what happens next.
// Outcomes: qualified | low_fit | not_job | duplicate. If Gemini fails, the lead is kept unscored.

const lead = $('Build AI Prompt').item.json;
const cfg = lead.config;
const resp = $input.first().json || {};

function dedupeSlug(s) {
  return String(s || '').toLowerCase()
    .replace(/\b(pvt|private|ltd|limited|inc|llc|co|company|corp)\b\.?/g, '')
    .replace(/[^a-z0-9]+/g, '');
}

let ai = null;
let aiError = '';
try {
  if (resp.error) throw new Error(resp.error.message || JSON.stringify(resp.error));
  const text = (resp.candidates?.[0]?.content?.parts || []).map((p) => p.text || '').join('').trim();
  if (!text) throw new Error('Empty Gemini response');
  ai = JSON.parse(text.replace(/^```(?:json)?\s*|\s*```$/g, ''));
} catch (e) {
  aiError = String(e.message || e).slice(0, 200);
}

const out = { ...lead };
delete out.geminiBody;
out.aiError = aiError;

if (ai) {
  out['Company'] = String(ai.company || '').trim() || lead['Company'];
  out['Job Title'] = String(ai.role || '').trim() || lead['Job Title'];
  out['Location'] = String(ai.location || '').trim() || lead['Location'];
  const score = Math.min(5, Math.max(1, Math.round(Number(ai.fit_score) || 1)));
  out['Fit Score'] = score;
  out['Fit Reason'] = String(ai.fit_reason || '').trim();
  out['Angle / Tip'] = String(ai.angle || '').trim();
} else {
  out['Fit Reason'] = `Not scored (AI error: ${aiError})`;
}

// Re-compute the dedupe key with the cleaner AI fields
out['Dedupe Key'] = out['Company'] && out['Job Title']
  ? `${lead.mode}|${dedupeSlug(out['Company'])}|${dedupeSlug(out['Job Title'])}` : '';

const knownKeys = new Set(lead.seenKeys || []);
for (const row of $('Load Existing Leads').all()) {
  const k = row.json && row.json['Dedupe Key'];
  if (k) knownKeys.add(String(k));
}

if (ai && ai.is_job_posting === false) out.outcome = 'not_job';
else if (out['Dedupe Key'] && knownKeys.has(out['Dedupe Key'])) out.outcome = 'duplicate';
else if (ai && out['Fit Score'] < cfg.minScore) out.outcome = 'low_fit';
else out.outcome = 'qualified';

out.qualified = out.outcome === 'qualified';
out.needContact = out.qualified && cfg.findContacts && Boolean(out['Company']);

return [{ json: out }];
