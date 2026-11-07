// Extract Contact
// Picks the first LinkedIn profile that clearly mentions the company. Leaves blanks if unsure.

const lead = $('Build Contact Query').item.json;
const resp = $input.first().json || {};
const out = { ...lead };
delete out.contactBody;

const results = Array.isArray(resp?.data?.web) ? resp.data.web
  : Array.isArray(resp?.data) ? resp.data : [];

const generic = new Set(['pvt', 'private', 'ltd', 'limited', 'inc', 'llc', 'the', 'and', 'company',
  'group', 'solutions', 'technologies', 'technology', 'tech', 'software', 'services', 'international']);
const tokens = String(lead['Company'] || '').toLowerCase().split(/[^a-z0-9]+/)
  .filter((t) => t.length >= 3 && !generic.has(t));

function parsePerson(title) {
  const cleaned = String(title || '').replace(/\s+/g, ' ').trim()
    .replace(/\s*[-–—|]\s*LinkedIn\s*$/i, '');
  const parts = cleaned.split(/\s+[-–—|]\s+/).map((s) => s.trim()).filter(Boolean);
  return { name: parts[0] || '', title: parts[1] || '' };
}

if (tokens.length) {
  for (const r of results) {
    const url = String(r.url || '');
    const m = url.match(/linkedin\.com\/in\/([^/?#]+)/i);
    if (!m) continue;
    const hay = `${r.title || ''} ${r.description || ''}`.toLowerCase();
    if (!tokens.some((t) => hay.includes(t))) continue;
    const p = parsePerson(r.title);
    out['Contact Name'] = p.name;
    out['Contact Title'] = p.title;
    out['Contact LinkedIn'] = `https://www.linkedin.com/in/${decodeURIComponent(m[1]).toLowerCase()}`;
    break;
  }
}

return [{ json: out }];
