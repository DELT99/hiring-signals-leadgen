// Run Summary
// One row per run for the "Run Log" tab: what was searched, by whom, and what happened.

const s = $input.first().json;
const cfg = s.config;
const models = cfg.aiModels || [];
const saved = s.savedByBoard || {};
const searches = Object.values(s.boardSearchIdx || {}).reduce((a, b) => a + Number(b || 0), 0);
const tbsLabel = { 'qdr:d': 'Past 24 hours', 'qdr:w': 'Past week', 'qdr:m': 'Past month', '': 'Any time' };

return [{
  json: {
    'Run ID': s.searchRunId,
    'Date': $now.toISODate(),
    'Time': $now.toFormat('HH:mm:ss'),
    'Run By': s.form['Your name'] || '',
    'Mode': s.modeLabel,
    'Roles': cfg.rolesText || '',
    'Locations': (cfg.locationsText || '') + (cfg.strictLocation ? '' : ' (not filtered)'),
    'Boards': (cfg.boards || []).map((b) => b.name).join(', '),
    'Posted Within': tbsLabel[cfg.tbs] ?? cfg.tbs,
    'Ranking': cfg.rankingLabel || '',
    'AI Model': cfg.useAi ? (models[s.aiModelIdxRun || 0] || '') + (s.aiDisabled ? ' (paused: errors)' : '') : '',
    'Min Score': cfg.rankingMode === 'none' ? '' : cfg.minScore,
    'Target': s.targetLeads,
    'Saved': s.newLeadsSaved,
    'Saved By Board': (cfg.boards || []).map((b) => `${b.name}: ${saved[b.name] || 0}`).join(', '),
    'Low Fit': s.lowFitCount,
    'Duplicates': s.duplicateCount,
    'Closed': s.closedCount,
    'Wrong Location': s.wrongLocationCount,
    'Not A Job': s.notJobCount,
    'Page Checked': s.pageCheckedCount,
    'Searches': searches,
    'Attempts': s.attemptIndex,
    'AI Errors': s.aiErrorCount,
    'Status': s.status,
    'Last Error': s.lastApiError || s.lastAiError || '',
  },
}];
