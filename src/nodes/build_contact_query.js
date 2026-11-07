// Build Contact Query
// Clients mode only: search LinkedIn profiles for a decision-maker at the hiring company.

const lead = $input.first().json;
const cfg = lead.config;

const company = String(lead['Company'] || '').replace(/"/g, '').trim();
const city = String(lead.form.Location || '').split(/[\/,|]/)[0].trim();
const cityPart = city && !/remote|anywhere|worldwide/i.test(city) ? city : '';
const roles = (cfg.contactRoles || []).join(' OR ');

const query = `site:linkedin.com/in/ "${company}" (${roles}) ${cityPart}`.replace(/\s+/g, ' ').trim();

return [{ json: { ...lead, contactBody: { query, limit: 5 } } }];
