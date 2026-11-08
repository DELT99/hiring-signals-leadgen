// Prepare Row
// Single entry point before writing to the sheet (with or without contact lookup).
// Maps the internal fields onto the clean, human-facing Leads columns.

const lead = $input.first().json;
const name = String(lead['Contact Name'] || '').trim();
const title = String(lead['Contact Title'] || '').trim();

return [{
  json: {
    ...lead,
    'Why It Fits': lead['Fit Reason'] || '',
    'Pitch / Tip': lead['Angle / Tip'] || '',
    'Contact': name ? (title ? `${name} (${title})` : name) : '',
    'Contact LinkedIn': lead['Contact LinkedIn'] || '',
    'Run ID': lead.searchRunId || lead['Search Run ID'] || '',
  },
}];
