// Tag Missed (no usable search result) / Tag Skipped (rejected by AI) share this logic
const lead = $input.first().json;
return [{
  json: {
    ...lead,
    outcome: lead.outcome && !['candidate', 'qualified', 'pending_ai'].includes(lead.outcome) ? lead.outcome : 'invalid',
  },
}];
