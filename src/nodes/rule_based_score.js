// Rule-Based Score
// Used when Ranking method is "Keyword ranking (no AI)" or "No ranking (save all)".
// No API calls. Produces the same fields as Parse AI Result so the rest of the flow is unchanged.

const lead = $input.first().json;
const cfg = lead.config;
const form = lead.form;
const out = { ...lead, aiError: '' };

const STOP = new Set(('and the for with from that this are you your our will have has who into able ' +
  'years year experience work working team teams strong good great skills skill job role looking ' +
  'want based plus etc also using use well can all any new more other per about over' +
  ' developer engineer senior junior lead').split(/\s+/));

const words = (s) => String(s || '').toLowerCase().split(/[^a-z0-9+#.]+/)
  .map((w) => w.replace(/\.+$/, '')).filter((w) => w.length >= 3 && !STOP.has(w));

// Known-keys duplicate check (same rule as the AI path)
const knownKeys = new Set(lead.seenKeys || []);
for (const row of $('Load Existing Leads').all()) {
  const k = row.json && row.json['Dedupe Key'];
  if (k) knownKeys.add(String(k));
}
const isDuplicate = Boolean(out['Dedupe Key']) && knownKeys.has(out['Dedupe Key']);

if (cfg.rankingMode === 'none') {
  out['Fit Score'] = '';
  out['Fit Reason'] = 'Not ranked';
  out.outcome = isDuplicate ? 'duplicate' : 'qualified';
} else {
  const title = String(lead.rawTitle || lead['Job Title'] || '').toLowerCase();
  const text = `${title} ${String(lead.Snippet || '').toLowerCase()}`;

  // 1) Role match: full phrase in title = 2, some role words in title = 1
  const rolePhrases = String(form['Role or skill keywords'] || '').toLowerCase()
    .split(/\s*,\s*|\s+or\s+/).map((s) => s.trim()).filter(Boolean);
  let rolePts = 0;
  let roleNote = 'no role match';
  if (rolePhrases.some((p) => title.includes(p))) { rolePts = 2; roleNote = 'role matches title'; }
  else if (rolePhrases.some((p) => words(p).some((w) => title.includes(w)))) { rolePts = 1; roleNote = 'role partly matches'; }

  const locs = String(form.Location || '').toLowerCase().split(/[\/,|]/).map((s) => s.trim()).filter(Boolean);
  const locWords = new Set(locs.flatMap((l) => words(l)));

  // 2) Skill overlap with the offer / CV summary (location words don't count as skills)
  const offerTerms = [...new Set(words(form['What you offer / your CV summary']))].filter((t) => !locWords.has(t));
  const hits = offerTerms.filter((t) => text.includes(t));
  const skillPts = hits.length >= 3 ? 2 : hits.length >= 1 ? 1 : 0;

  // 3) Location match
  const locText = `${text} ${String(lead.Location || '').toLowerCase()}`;
  const locPts = locs.some((l) => locText.includes(l)) ? 1 : 0;

  const score = Math.min(5, 1 + rolePts + skillPts + locPts);
  out['Fit Score'] = score;
  out['Fit Reason'] = `Keyword score: ${roleNote}; ${hits.length} skill match(es)` +
    (hits.length ? ` (${hits.slice(0, 5).join(', ')})` : '') + (locPts ? '; location matches' : '');

  if (isDuplicate) out.outcome = 'duplicate';
  else if (score < cfg.minScore) out.outcome = 'low_fit';
  else out.outcome = 'qualified';
}

out['Angle / Tip'] = out['Angle / Tip'] || '';
out.qualified = out.outcome === 'qualified';
out.needContact = out.qualified && cfg.findContacts && Boolean(out['Company']);

return [{ json: out }];
