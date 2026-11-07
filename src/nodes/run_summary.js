// Run Summary
// Final stats for the execution log and the "Run Log" sheet tab.

const s = $input.first().json;
const skipped = Number(s.lowFitCount || 0) + Number(s.duplicateCount || 0) + Number(s.notJobCount || 0);

return [{
  json: {
    'Run ID': s.searchRunId,
    'Date': $now.toISODate(),
    'Time': $now.toFormat('HH:mm:ss'),
    'Mode': s.modeLabel,
    'Run By': s.form['Your name'] || '',
    'Keywords': s.form['Role or skill keywords'] || '',
    'Location': s.form.Location || '',
    'Ranking': s.config.rankingLabel || '',
    'Boards': (s.config.boards || []).map((b) => b.name).join(', '),
    'Target': s.targetLeads,
    'Saved': s.newLeadsSaved,
    'Skipped': skipped,
    'Low Fit': s.lowFitCount,
    'Duplicates': s.duplicateCount,
    'Attempts': s.attemptIndex,
    'AI Errors': s.aiErrorCount,
    'Status': s.status,
    'Last Error': s.lastApiError || '',
  },
}];
