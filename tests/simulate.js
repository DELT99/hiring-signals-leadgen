// Offline simulation of the workflow graph with mocked Firecrawl, Gemini and Google Sheets.
// Runs the real Code-node sources from workflow/hiring-signal-lead-engine.json.
//   node tests/simulate.js
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const wf = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'workflow', 'hiring-signal-lead-engine.json'), 'utf8'));
const byName = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

// Skip real waiting
global.setTimeout = (fn) => { fn(); return 0; };

const now = {
  toISODate: () => '2026-11-07',
  toFormat: () => '22:30:00',
  toISO: () => '2026-11-07T22:30:00+05:00',
};

function evalIf(node, item) {
  const expr = node.parameters.conditions.conditions[0].leftValue; // ={{ $json.x }}
  const keyPath = expr.match(/\$json\.([\w.]+)/)[1].split('.');
  const value = keyPath.reduce((o, k) => (o == null ? o : o[k]), item);
  return value === true ? 0 : 1;
}

function runWorkflow({ form, existingRows, mocks, maxSteps = 20000 }) {
  const last = {};
  const appended = { Leads: [], 'Run Log': [] };
  const calls = { firecrawl: 0, gemini: 0, contact: 0, scrape: 0, geminiModels: [], scrapedUrls: [] };
  const scrape = mocks.scrape || (() => ({ success: true, data: { markdown: '# Job\nApply now', metadata: { statusCode: 200 } } }));

  async function exec(node, input) {
    const t = node.type;
    if (t === 'n8n-nodes-base.formTrigger') return [[form]];
    if (t === 'n8n-nodes-base.googleSheets' && node.parameters.operation === 'read') {
      return [existingRows.length ? existingRows : [{}]];
    }
    if (t === 'n8n-nodes-base.googleSheets' && node.parameters.operation === 'append') {
      const row = {};
      for (const col of Object.keys(node.parameters.columns.value)) row[col] = input[col];
      appended[node.parameters.sheetName.value].push(row);
      return [[row]];
    }
    if (t === 'n8n-nodes-base.if') {
      const out = [[], []];
      out[evalIf(node, input)].push(input);
      return out;
    }
    if (t === 'n8n-nodes-base.httpRequest') {
      if (node.name === 'Firecrawl Search') { calls.firecrawl++; return [[mocks.firecrawl(input.firecrawlBody, calls.firecrawl)]]; }
      if (node.name === 'Gemini Qualify') {
        calls.gemini++; calls.geminiModels.push(input.aiModelCurrent);
        return [[mocks.gemini(input.geminiBody, input.aiModelCurrent, calls.gemini)]];
      }
      if (node.name === 'Firecrawl Page Check') { calls.scrape++; calls.scrapedUrls.push(input.scrapeBody.url); return [[scrape(input.scrapeBody)]]; }
      if (node.name === 'Firecrawl Contact Search') { calls.contact++; return [[mocks.contact(input.contactBody)]]; }
    }
    if (t === 'n8n-nodes-base.code') {
      if (process.env.TRACE && node.name === 'Update Counters') console.log('   pass:', input.useQueue ? 'queue ' : 'search', input.currentBoard, '->', input.outcome, input['Job Board'] || '', JSON.stringify(input.savedByBoard), 'q=' + (input.candidateQueue || []).map((c) => c.board[0]).join(''));
      const $ = (name) => ({
        item: { json: last[name] },
        first: () => ({ json: last[name] }),
        all: () => (name === 'Load Existing Leads'
          ? (existingRows.length ? existingRows : [{}]).map((j) => ({ json: j }))
          : [{ json: last[name] }]),
      });
      const $input = { first: () => ({ json: input }), all: () => [{ json: input }] };
      const fn = new AsyncFunction('$input', '$', '$now', '$execution', node.parameters.jsCode);
      const res = await fn($input, $, now, { id: 'sim-1' });
      if (process.env.TRACE && node.name === 'Build Search Query') console.log('   build:', JSON.stringify(input.savedByBoard), '->', res[0].json.useQueue ? 'queue ' + res[0].json.currentBoard : 'search ' + res[0].json.currentBoard);
      return [res.map((r) => r.json)];
    }
    throw new Error(`No executor for ${node.name} (${t})`);
  }

  return (async () => {
    let queue = [{ name: 'Lead Intake Form', input: null }];
    let steps = 0;
    while (queue.length) {
      if (++steps > maxSteps) throw new Error('Too many steps (infinite loop?)');
      const { name, input } = queue.shift();
      const outputs = await exec(byName[name], input);
      const conns = (wf.connections[name] || {}).main || [];
      outputs.forEach((items, idx) => {
        if (!items.length) return;
        last[name] = items[0];
        for (const target of conns[idx] || []) queue.push({ name: target.node, input: items[0] });
      });
    }
    return { appended, calls, last };
  })();
}

// ---------- mocks ----------
const companies = ['Arbisoft', 'Systems Ltd', 'Netsol', 'Tkxel', 'Devsinc', 'Folio3', 'Venturedive',
  'Confiz', 'Techlogix', 'Contour Software', 'Bitsol', 'Cubix', 'Rolustech', '10Pearls', 'Motive'];

function firecrawlMock(body, n) {
  const site = (body.query.match(/site:(\S+)/) || [])[1] || 'any';
  const web = [];
  for (let i = 0; i < 10; i++) {
    const k = (n * 7 + i) % 60;
    const company = companies[k % companies.length];
    if (i === 0) { web.push({ url: 'https://pk.indeed.com/q-flutter-l-lahore-jobs.html', title: '120 Flutter Developer jobs in Lahore (with salaries)' }); continue; }
    if (site.startsWith('linkedin')) {
      web.push({ url: `https://pk.linkedin.com/jobs/view/flutter-developer-at-${company.toLowerCase().replace(/\s/g, '-')}-${4000000000 + k}?trk=x`,
        title: `${company} hiring Flutter Developer in ${k % 7 === 3 ? 'Karachi, Sindh' : 'Lahore, Punjab'}, Pakistan | LinkedIn`,
        description: k % 4 === 0 ? 'No longer accepting applications. Flutter developer role.'
          : k % 5 === 0 ? '3 weeks ago · Build cross-platform apps in Flutter.'
          : '2 days ago · Build cross-platform apps in Flutter. 2+ years.' });
    } else if (site.startsWith('rozee')) {
      web.push({ url: `https://www.rozee.pk/${company.toLowerCase().replace(/\s/g, '-')}-mobile-app-developer-lahore-jobs-${1500000 + k}`,
        title: `Mobile App Developer Job in Lahore at ${company} - Rozee.pk`, description: 'Flutter / React Native.' });
    } else {
      web.push({ url: `https://pk.indeed.com/viewjob?jk=abc${k}&from=serp`,
        title: `Senior Flutter Engineer - ${company} - Lahore | Indeed.com`, description: 'Dart, Flutter, Firebase.' });
    }
  }
  return { success: true, data: { web } };
}

function geminiMock(body) {
  const text = body.contents[0].parts[0].text;
  const title = (text.match(/Title: (.*)/) || [])[1] || '';
  let h = 0; for (const ch of title) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const m = title.match(/^(.+?) hiring (.+?) in/) || title.match(/ at (.+?) -/) || title.match(/- (.+?) -/);
  const company = m ? (m[1].includes('hiring') ? m[1] : m[1]) : '';
  const verdict = {
    is_job_posting: h % 13 !== 0,
    is_open: true,
    company: (title.match(/^(.+?) hiring/) || [])[1] || (title.match(/ at (.+?) - Rozee/) || [])[1] || (title.match(/- (.+?) - Lahore/) || [])[1] || company,
    role: /Mobile App/.test(title) ? 'Mobile App Developer' : /Senior/.test(title) ? 'Senior Flutter Engineer' : 'Flutter Developer',
    location: (title.match(/ in ([^|]+?) \|/) || [])[1] || 'Lahore, Pakistan',
    fit_score: 1 + (h % 5),
    fit_reason: 'Needs Flutter devs, which matches the offer.',
    angle: 'Offer a dedicated Flutter squad to clear their backlog.',
  };
  return { candidates: [{ content: { parts: [{ text: JSON.stringify(verdict) }] } }] };
}

function contactMock(body) {
  const company = (body.query.match(/"([^"]+)"/) || [])[1] || 'X';
  return { success: true, data: { web: [
    { url: 'https://pk.linkedin.com/in/random-person', title: 'Random Person - CTO - OtherCo | LinkedIn' },
    { url: `https://pk.linkedin.com/in/ali-${company.toLowerCase().replace(/\s/g, '')}`, title: `Ali Raza - CTO - ${company} | LinkedIn`, description: `CTO at ${company}` },
  ] } };
}

const baseForm = {
  Mode: 'Find clients (companies that are hiring)',
  'Your name': 'Talha',
  Roles: ['Flutter Developer', 'Mobile App Developer'],
  'Other roles (comma-separated)': '',
  'Locations (cities or countries, comma-separated)': 'Lahore, Remote',
  'Quick-pick locations': [],
  'Location filter': 'Only keep jobs in my locations (or remote)',
  'Job boards': ['LinkedIn Jobs', 'Rozee.pk', 'Indeed'],
  'Posted within': 'Past week',
  'What you offer / your CV summary': 'We are a Flutter agency in Lahore offering dedicated mobile teams.',
  'Ranking method': 'AI ranking (Gemini)',
  'Minimum fit score (1-5)': '3',
  'Find a decision-maker? (clients mode)': 'Yes',
  'Maximum leads': '10',
};

// Dedupe key as the workflow computes it from a Leads row
const slug = (x) => String(x || '').toLowerCase().replace(/\b(pvt|private|ltd|limited|inc|llc|co|company|corp)\b\.?/g, '').replace(/[^a-z0-9]+/g, '');
const keyOf = (l) => `${String(l.Mode).toLowerCase().startsWith('job') ? 'jobs' : 'clients'}|${slug(l.Company)}|${slug(l['Job Title'])}`;
const liK = (l) => Number((String(l['Job URL']).match(/jobs\/view\/(\d+)/) || [])[1]) - 4000000000;
const byBoard = (leads) => leads.reduce((m, l) => ((m[l['Job Board']] = (m[l['Job Board']] || 0) + 1), m), {});

// Plenty of unique, valid results on every board (nothing ever duplicates or runs dry)
function uniqueMock(b, n) {
    const site = (b.query.match(/site:(\S+)/) || [])[1] || '';
  return { success: true, data: { web: [1, 2].map((i) => {
    const id = n * 10 + i;
    if (site.startsWith('rozee')) return { url: `https://www.rozee.pk/co${id}-flutter-developer-lahore-jobs-${2000000 + id}`, title: `Flutter Developer Job in Lahore at Co${id} - Rozee.pk`, description: '2 days ago' };
    if (site.startsWith('indeed')) return { url: `https://pk.indeed.com/viewjob?jk=u${id}`, title: `Flutter Developer - Co${id} - Lahore | Indeed.com`, description: '2 days ago' };
    return { url: `https://www.linkedin.com/jobs/view/${5000000000 + id}`, title: `Co${id} hiring Flutter Developer in Lahore, Punjab, Pakistan | LinkedIn`, description: '2 days ago' };
  }) } };
}

const okMocks = { firecrawl: firecrawlMock, gemini: geminiMock, contact: contactMock };
const geminiErr = (code, message, extra = {}) => ({ error: { code, message, ...extra } });

(async () => {
  const existing = [{ Mode: 'Clients', 'Job URL': 'https://www.linkedin.com/jobs/view/4000000007', 'Dedupe Key': 'clients|devsinc|flutterdeveloper' }];

  // 1) Clients mode happy path
  const r1 = await runWorkflow({ form: baseForm, existingRows: existing, mocks: okMocks });
  const leads = r1.appended.Leads;
  const log = r1.appended['Run Log'][0];
  console.log('1 Clients:', log.Status, `saved=${log.Saved}`, `closed=${log.Closed}`, `pageChecked=${log['Page Checked']}`, `byBoard=${log['Saved By Board']}`, `attempts=${log.Attempts}`,
    { firecrawl: r1.calls.firecrawl, gemini: r1.calls.gemini, scrape: r1.calls.scrape, contact: r1.calls.contact });
  assert.strictEqual(log.Status, 'target_reached');
  assert.strictEqual(leads.length, 10);
  assert.ok(leads.every((l) => Number(l['Fit Score']) >= 3), 'all saved leads meet min score');
  assert.ok(!leads.some((l) => l['Job URL'] === 'https://www.linkedin.com/jobs/view/4000000007'), 'existing URL skipped');
  assert.ok(!leads.some((l) => /indeed\.com\/q-/.test(l['Job URL'])), 'listing pages skipped');
  assert.strictEqual(new Set(leads.map((l) => l['Job URL'])).size, leads.length, 'no duplicate URLs');
  const keys = leads.map(keyOf);
  assert.strictEqual(new Set(keys).size, keys.length, 'no duplicate company+role');
  assert.ok(!keys.includes('clients|devsinc|flutterdeveloper'), 'existing dedupe key skipped');
  assert.ok(leads.some((l) => l['Contact LinkedIn'].includes('/in/ali-')), 'contact found');
  assert.ok(!leads.some((l) => l['Contact LinkedIn'].includes('random-person')), 'wrong-company contact rejected');
  const li = leads.filter((l) => /linkedin/.test(l['Job URL']));
  assert.ok(li.every((l) => liK(l) % 4 !== 0), 'closed LinkedIn snippets never saved');
  assert.ok(li.every((l) => liK(l) % 5 !== 0), 'stale postings (older than window) never saved');
  assert.ok(!r1.calls.scrapedUrls.some((u) => /linkedin/.test(u)), 'LinkedIn never page-checked');
  assert.ok(leads.filter((l) => !/linkedin/.test(l['Job URL'])).every((l) => r1.calls.scrapedUrls.includes(l['Job URL'])), 'other boards page-checked');
  assert.strictEqual(Number(log['Page Checked']), r1.calls.scrape);
  assert.deepStrictEqual(Object.keys(leads[0]), ['Date Added', 'Mode', 'Company', 'Job Title', 'Location', 'Posted', 'Job Board', 'Job URL', 'Fit Score', 'Why It Fits', 'Pitch / Tip', 'Contact', 'Contact LinkedIn', 'Status', 'Run ID'], 'lean Leads columns');
  assert.ok(leads.some((l) => / \(CTO\)$/.test(l.Contact)), 'contact shown as "Name (Title)"');
  assert.ok(Number(log.Closed) > 0, 'closed postings counted');
  console.log('  sample lead:', JSON.stringify(leads[0]));
  console.log('  run log:', JSON.stringify(log));

  // 2) Jobs mode: no contact lookup
  const r2 = await runWorkflow({ form: { ...baseForm, Mode: 'Find jobs for me' }, existingRows: existing, mocks: okMocks });
  console.log('2 Jobs:', r2.appended['Run Log'][0].Status, `saved=${r2.appended.Leads.length}`, `contact=${r2.calls.contact}`);
  assert.strictEqual(r2.calls.contact, 0);
  assert.ok(r2.appended.Leads.every((l) => l.Mode === 'Jobs' && l.Status === 'To apply'));

  // 3) Firecrawl out of credits -> stop after 3 API errors
  const r3 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, firecrawl: () => ({ success: false, error: 'Insufficient credits' }) } });
  const l3 = r3.appended['Run Log'][0];
  console.log('3 Firecrawl down:', l3.Status, `attempts=${l3.Attempts}`, l3['Last Error']);
  assert.strictEqual(l3.Status, 'api_error');
  assert.strictEqual(r3.calls.firecrawl, 3);

  // 4) Gemini flaky: 503 "high demand" / timeouts on the first model, then works -> retries + model fallback, no fallback scores
  let busy = 0;
  const flaky = (body, model, n) => {
    if (model === 'gemini-3.5-flash-lite' && busy++ < 6) {
      return busy % 2 ? geminiErr(503, 'This model is currently experiencing high demand. Spikes in demand are usually temporary.')
        : { error: { message: 'timeout of 30000ms exceeded' } };
    }
    return geminiMock(body);
  };
  const r4 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, gemini: flaky } });
  const l4 = r4.appended['Run Log'][0];
  console.log('4 Gemini flaky:', l4.Status, `saved=${l4.Saved}`, `aiErrors=${l4['AI Errors']}`, `model=${l4['AI Model']}`,
    'models used:', [...new Set(r4.calls.geminiModels)].join(', '));
  assert.strictEqual(l4.Status, 'target_reached');
  assert.strictEqual(Number(l4['AI Errors']), 0, 'retries recovered every lead');
  assert.ok(r4.calls.geminiModels.includes('gemini-3.5-flash'), 'fell back to second model');
  assert.ok(r4.appended.Leads.every((l) => !/AI unavailable/.test(l['Why It Fits'])));

  // 5) Gemini completely down -> keyword fallback, then AI paused for the run (no wasted calls)
  const r5 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, gemini: () => geminiErr(503, 'This model is currently experiencing high demand.') } });
  const l5 = r5.appended['Run Log'][0];
  console.log('5 Gemini down:', l5.Status, `saved=${l5.Saved}`, `geminiCalls=${r5.calls.gemini}`, `aiErrors=${l5['AI Errors']}`, `model=${l5['AI Model']}`);
  assert.strictEqual(l5.Status, 'target_reached');
  assert.ok(r5.calls.gemini <= 3 * 4, 'gives up after 3 failed postings x 4 attempts');
  assert.ok(r5.appended.Leads.every((l) => /^Keyword score/.test(l['Why It Fits'])), 'keyword fallback used');
  assert.ok(r5.appended.Leads.some((l) => /AI paused/.test(l['Why It Fits'])), 'AI paused after repeated failures');
  assert.ok(/paused/.test(l5['AI Model']));

  // 6) Invalid key -> no retries, AI paused immediately
  const r6 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, gemini: () => geminiErr(400, 'API key not valid. Please pass a valid API key.') } });
  console.log('6 Bad key:', r6.appended['Run Log'][0].Status, `geminiCalls=${r6.calls.gemini}`);
  assert.strictEqual(r6.calls.gemini, 1);

  // 7) Model rejects thinkingConfig -> retried without it, run remembers
  let thinkErrs = 0;
  const noThink = (body) => body.generationConfig.thinkingConfig
    ? (thinkErrs++, geminiErr(400, 'Invalid JSON payload: Unknown name "thinkingLevel" at generation_config.thinking_config'))
    : geminiMock(body);
  const r7 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, gemini: noThink } });
  console.log('7 No-thinking model:', r7.appended['Run Log'][0].Status, `thinkingErrors=${thinkErrs}`, `aiErrors=${r7.appended['Run Log'][0]['AI Errors']}`);
  assert.strictEqual(thinkErrs, 1, 'only the first call fails; the run stops sending thinkingConfig');

  // 8) Rate limit 429 with retryDelay -> waits and retries
  let rl = 0;
  const rate = (body) => (rl++ % 3 === 0 ? geminiErr(429, 'Resource has been exhausted (e.g. check quota).', { details: [{ '@type': 'type.googleapis.com/google.rpc.RetryInfo', retryDelay: '7s' }] }) : geminiMock(body));
  const r8 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, gemini: rate } });
  console.log('8 Rate limited:', r8.appended['Run Log'][0].Status, `aiErrors=${r8.appended['Run Log'][0]['AI Errors']}`);
  assert.strictEqual(Number(r8.appended['Run Log'][0]['AI Errors']), 0);

  // 9) Page check finds closed pages (404 / banner / redirect) -> not saved
  const closedPages = (b) => {
    const u = b.url;
    if (/jobs-15000\d[02468]$/.test(u)) return { success: true, data: { markdown: '# Mobile App Developer\nThis job has expired.', metadata: { statusCode: 200 } } };
    if (/jk=abc\d*[05]$/.test(u)) return { success: true, data: { markdown: '', metadata: { statusCode: 404 } } };
    return { success: true, data: { markdown: '# Job\nPosted 2 days ago. Apply now.', metadata: { statusCode: 200 } } };
  };
  const r9 = await runWorkflow({ form: { ...baseForm, 'Job boards': ['Rozee.pk', 'Indeed'] }, existingRows: [], mocks: { ...okMocks, scrape: closedPages } });
  const l9 = r9.appended['Run Log'][0];
  console.log('9 Page check:', l9.Status, `saved=${l9.Saved}`, `closed=${l9.Closed}`, `scrapes=${r9.calls.scrape}`);
  assert.ok(Number(l9.Closed) > 0);
  assert.ok(!r9.appended.Leads.some((l) => /jobs-15000\d[02468]$/.test(l['Job URL']) || /jk=abc\d*[05]$/.test(l['Job URL'])), 'closed pages never saved');

  // 10) Page check off -> no scrapes
  const r10 = await runWorkflow({ form: { ...baseForm, 'Check job is still open? (extra credits)': 'No' }, existingRows: [], mocks: okMocks });
  console.log('10 Page check off:', `scrapes=${r10.calls.scrape}`);
  assert.strictEqual(r10.calls.scrape, 0);

  // 11) Keyword ranking: no Gemini calls
  const kwMocks = { ...okMocks, gemini: () => { throw new Error('Gemini must not be called'); } };
  const r11 = await runWorkflow({ form: { ...baseForm, 'Ranking method': 'Keyword ranking (no AI)' }, existingRows: existing, mocks: kwMocks });
  const l11 = r11.appended['Run Log'][0];
  console.log('11 Keyword:', l11.Status, `saved=${l11.Saved}`, `ranking=${l11.Ranking}`);
  assert.strictEqual(r11.calls.gemini, 0);
  assert.ok(r11.appended.Leads.every((l) => Number(l['Fit Score']) >= 3 && l['Why It Fits'].startsWith('Keyword score')));

  // 12) No ranking: save every valid, open, non-duplicate posting
  const r12 = await runWorkflow({ form: { ...baseForm, 'Ranking method': 'No ranking (save all)', 'Find a decision-maker? (clients mode)': 'No' }, existingRows: existing, mocks: kwMocks });
  const l12 = r12.appended['Run Log'][0];
  console.log('12 No ranking:', l12.Status, `saved=${l12.Saved}`);
  assert.strictEqual(r12.calls.gemini, 0);
  assert.ok(r12.appended.Leads.every((l) => l['Fit Score'] === '' && l['Why It Fits'] === 'Not ranked'));

  // 13) Nothing found -> retry limit, no crash
  const r13 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, firecrawl: () => ({ success: true, data: { web: [] } }) } });
  console.log('13 Empty:', r13.appended['Run Log'][0].Status, `attempts=${r13.appended['Run Log'][0].Attempts}`);
  assert.strictEqual(r13.appended['Run Log'][0].Status, 'retry_limit_reached');

  // 14) Query exclusions are present
  let q = '';
  await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, firecrawl: (b, n) => { q = q || b.query; return firecrawlMock(b, n); } } });
  console.log('14 Query:', q);
  assert.ok(q.includes('-"no longer accepting"'));

  // 15) Multiple roles x locations: every combination is searched on every board
  const queries = [];
  const multiForm = { ...baseForm, Roles: ['Flutter Developer', 'AI Engineer'], 'Locations (cities or countries, comma-separated)': 'Lahore, Karachi', 'Quick-pick locations': ['Remote'], 'Maximum leads': '50',
    'Ranking method': 'No ranking (save all)', 'Location filter': 'Keep all results' };  // every search succeeds -> no broadening
  await runWorkflow({ form: multiForm, existingRows: [], mocks: { ...okMocks, firecrawl: (b, n) => { queries.push(b.query); return uniqueMock(b, n); } } });
  if (process.env.DEBUG) console.log(queries.slice(0, 18).join("\n"));
  const combosSeen = new Set();
  for (const q of queries.slice(0, 18)) {
    const role = /Flutter Developer/.test(q) ? 'Flutter' : /AI Engineer/.test(q) ? 'AI' : '?';
    const loc = /"Lahore"|Lahore/.test(q) ? 'Lahore' : /Karachi/.test(q) ? 'Karachi' : /remote/.test(q) ? 'Remote' : '?';
    const site = (q.match(/site:(\S+)/) || [])[1];
    combosSeen.add(`${role}|${loc}|${site}`);
  }
  console.log('15 Multi roles/locations:', `searches=${queries.length}`, `distinct role|location|board in first 18 = ${combosSeen.size}`);
  assert.strictEqual(combosSeen.size, 18, '2 roles x 3 locations x 3 boards all searched');

  // 16) Location filter: only Lahore picked -> Karachi jobs skipped; "Keep all" -> kept
  const lahoreOnly = { ...baseForm, 'Locations (cities or countries, comma-separated)': 'Lahore', 'Maximum leads': '25' };
  const r16 = await runWorkflow({ form: lahoreOnly, existingRows: [], mocks: okMocks });
  const kar16 = r16.appended.Leads.filter((l) => /karachi/i.test(`${l.Location} ${l['Job Title']}`));
  console.log('16a Strict location:', `saved=${r16.appended.Leads.length}`, `karachiSaved=${kar16.length}`, `wrongLocation=${r16.appended['Run Log'][0]['Wrong Location']}`);
  assert.strictEqual(kar16.length, 0);
  const r16b = await runWorkflow({ form: { ...lahoreOnly, 'Location filter': 'Keep all results' }, existingRows: [], mocks: okMocks });
  const kar16b = r16b.appended.Leads.filter((l) => /karachi/i.test(l.Location));
  console.log('16b Keep all:', `karachiSaved=${kar16b.length}`, `logLocations=${r16b.appended['Run Log'][0].Locations}`);
  assert.ok(kar16b.length > 0);

  // 17) Country pick accepts its cities: "Pakistan (anywhere)" keeps Lahore AND Karachi
  const r17 = await runWorkflow({ form: { ...baseForm, 'Locations (cities or countries, comma-separated)': '', 'Quick-pick locations': ['Pakistan'], 'Maximum leads': '25' }, existingRows: [], mocks: okMocks });
  console.log('17 Country:', `saved=${r17.appended.Leads.length}`, `karachi=${r17.appended.Leads.filter((l) => /karachi/i.test(l.Location)).length}`);
  assert.ok(r17.appended.Leads.some((l) => /karachi/i.test(l.Location)) && r17.appended.Leads.some((l) => /lahore/i.test(l.Location)));

  // 18) Old single-text form fields still work
  const oldForm = { ...baseForm, Roles: undefined, 'Locations (cities or countries, comma-separated)': undefined, 'Role or skill keywords': 'Flutter developer, UI/UX Designer', Location: 'Lahore / Remote' };
  const r18 = await runWorkflow({ form: oldForm, existingRows: [], mocks: okMocks });
  console.log('18 Old fields:', r18.appended['Run Log'][0].Status, `roles="${r18.appended['Run Log'][0].Roles}"`);
  assert.strictEqual(r18.appended['Run Log'][0].Roles, 'Flutter developer, UI/UX Designer');

  // 19) No role picked -> clear error
  await assert.rejects(runWorkflow({ form: { ...baseForm, Roles: [] }, existingRows: [], mocks: okMocks }), /at least one role/);
  console.log('19 Validation: clear error when no role picked');

  // 20) Board balance: 3 boards, 10 leads -> every board contributes (share = 4 each)
  for (const target of ['10', '25']) {
    const r20 = await runWorkflow({ form: { ...baseForm, 'Maximum leads': target, 'Ranking method': 'No ranking (save all)' }, existingRows: [], mocks: { ...okMocks, firecrawl: uniqueMock } });
    const bb = byBoard(r20.appended.Leads);
    console.log(`20 Balance (target ${target}):`, JSON.stringify(bb), `| run log: ${r20.appended['Run Log'][0]['Saved By Board']}`);
    const share = Math.ceil(Number(target) / 3);
    if (process.env.DEBUG) console.log(r20.appended["Run Log"][0]);
    for (const b of ['LinkedIn Jobs', 'Rozee.pk', 'Indeed']) assert.ok((bb[b] || 0) >= share - 1 && (bb[b] || 0) <= share, `${b} gets a fair share`);
  }

  // 21) A dry board (Indeed returns only listing pages) -> the other boards fill its share
  const dryIndeed = (b, n) => (/site:indeed/.test(b.query)
    ? { success: true, data: { web: [{ url: 'https://pk.indeed.com/q-flutter-l-lahore-jobs.html', title: 'Flutter Developer Jobs in Lahore (with salaries)' },
      { url: 'https://pk.indeed.com/jobs?q=flutter&l=lahore', title: 'Flutter jobs in Lahore' }] } }
    : firecrawlMock(b, n));
  const r21 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { ...okMocks, firecrawl: dryIndeed } });
  const bb21 = byBoard(r21.appended.Leads);
  console.log('21 Dry board:', r21.appended['Run Log'][0].Status, JSON.stringify(bb21));
  assert.strictEqual(r21.appended['Run Log'][0].Status, 'target_reached');
  assert.ok(!bb21.Indeed && bb21['LinkedIn Jobs'] > 0 && bb21['Rozee.pk'] > 0);

  // 22) Only one board selected -> works as before
  const r22 = await runWorkflow({ form: { ...baseForm, 'Job boards': ['Rozee.pk'], 'Ranking method': 'No ranking (save all)' }, existingRows: [], mocks: { ...okMocks, firecrawl: uniqueMock } });
  console.log('22 Single board:', r22.appended['Run Log'][0].Status, JSON.stringify(byBoard(r22.appended.Leads)));
  assert.strictEqual(r22.appended.Leads.length, 10);

  // 23) Worldwide: typed "Berlin, London" -> Munich/Paris jobs skipped, Berlin/London kept, unknown places kept
  const cityMock = (b, n) => {
    const places = ['Berlin, Germany', 'Munich, Germany', 'London, England, United Kingdom', 'Paris, France', 'Lisbon', 'Remote'];
    return { success: true, data: { web: places.map((pl, i) => ({ url: `https://www.linkedin.com/jobs/view/${6000000000 + n * 10 + i}`,
      title: `W${n}x${i} hiring Flutter Developer in ${pl} | LinkedIn`, description: '1 day ago' })) } };
  };
  const world = { ...baseForm, 'Locations (cities or countries, comma-separated)': 'Berlin, London', 'Job boards': ['LinkedIn Jobs'], 'Ranking method': 'No ranking (save all)', 'Maximum leads': '25' };
  const r23 = await runWorkflow({ form: world, existingRows: [], mocks: { ...okMocks, firecrawl: cityMock } });
  const locs23 = r23.appended.Leads.map((l) => l.Location);
  console.log('23 Worldwide cities:', `saved=${locs23.length}`, [...new Set(locs23.map((x) => x.split(',')[0]))].join(' | '), `wrongLocation=${r23.appended['Run Log'][0]['Wrong Location']}`);
  assert.ok(!locs23.some((l) => /munich|paris/i.test(l)), 'other known cities skipped');
  assert.ok(locs23.some((l) => /berlin/i.test(l)) && locs23.some((l) => /london/i.test(l)), 'picked cities kept');

  // 24) Country typed: "Germany" accepts Berlin and Munich, rejects London/Paris
  const r24 = await runWorkflow({ form: { ...world, 'Locations (cities or countries, comma-separated)': 'Germany' }, existingRows: [], mocks: { ...okMocks, firecrawl: cityMock } });
  const locs24 = r24.appended.Leads.map((l) => l.Location);
  console.log('24 Country:', [...new Set(locs24.map((x) => x.split(',')[0]))].join(' | '));
  assert.ok(locs24.some((l) => /munich/i.test(l)) && locs24.some((l) => /berlin/i.test(l)) && !locs24.some((l) => /london|paris/i.test(l)));

  // 25) "Anywhere (no location filter)": no location in the query, nothing filtered
  let q25 = '';
  const r25 = await runWorkflow({ form: { ...world, 'Locations (cities or countries, comma-separated)': '', 'Quick-pick locations': ['Anywhere (no location filter)'] }, existingRows: [],
    mocks: { ...okMocks, firecrawl: (b, n) => { q25 = q25 || b.query; return cityMock(b, n); } } });
  console.log('25 Anywhere:', `query="${q25}"`, `wrongLocation=${r25.appended['Run Log'][0]['Wrong Location']}`);
  assert.ok(!/"Anywhere"|anywhere/i.test(q25.replace(/-"[^"]+"/g, '')), 'no location term in query');
  assert.strictEqual(Number(r25.appended['Run Log'][0]['Wrong Location']), 0);

  // 26) Typed + quick-pick are combined; validation message for no location
  const r26 = await runWorkflow({ form: { ...baseForm, 'Locations (cities or countries, comma-separated)': 'Toronto', 'Quick-pick locations': ['Remote', 'Canada'] }, existingRows: [], mocks: okMocks });
  console.log('26 Combined:', `locations="${r26.appended['Run Log'][0].Locations}"`);
  assert.strictEqual(r26.appended['Run Log'][0].Locations, 'Toronto, Remote, Canada');
  await assert.rejects(runWorkflow({ form: { ...baseForm, 'Locations (cities or countries, comma-separated)': '', 'Quick-pick locations': [] }, existingRows: [], mocks: okMocks }), /at least one location/);

  console.log('\nAll checks passed.');
})().catch((e) => { console.error(e); process.exit(1); });
