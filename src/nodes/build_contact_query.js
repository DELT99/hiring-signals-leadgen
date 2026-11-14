// Build Contact Query
// Clients mode only: search LinkedIn profiles for a decision-maker at the hiring company.

const lead = $input.first().json;
const cfg = lead.config;

const company = String(lead['Company'] || '').replace(/"/g, '').trim();
// The location this job matched, else the first non-remote location picked on the form
const city = String(lead.matchedLocation || (cfg.locations || []).find((l) => !/remote|anywhere|worldwide|global/i.test(l)) || '').trim();
const cityPart = city && !/remote|anywhere|worldwide|global/i.test(city) ? city : '';
const roles = (cfg.contactRoles || []).join(' OR ');

const query = `site:linkedin.com/in/ "${company}" (${roles}) ${cityPart}`.replace(/\s+/g, ' ').trim();

return [{ json: { ...lead, contactBody: { query, limit: 5 } } }];
