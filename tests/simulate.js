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
  const calls = { firecrawl: 0, gemini: 0, contact: 0 };

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
      if (node.name === 'Gemini Qualify') { calls.gemini++; return [[mocks.gemini(input.geminiBody)]]; }
      if (node.name === 'Firecrawl Contact Search') { calls.contact++; return [[mocks.contact(input.contactBody)]]; }
    }
    if (t === 'n8n-nodes-base.code') {
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
        title: `${company} hiring Flutter Developer in Lahore, Punjab, Pakistan | LinkedIn`, description: 'Build cross-platform apps in Flutter. 2+ years.' });
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
    company: (title.match(/^(.+?) hiring/) || [])[1] || (title.match(/ at (.+?) - Rozee/) || [])[1] || (title.match(/- (.+?) - Lahore/) || [])[1] || company,
    role: /Mobile App/.test(title) ? 'Mobile App Developer' : /Senior/.test(title) ? 'Senior Flutter Engineer' : 'Flutter Developer',
    location: 'Lahore, Pakistan',
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
  'Role or skill keywords': 'Flutter developer, Mobile app developer',
  Location: 'Lahore / Remote',
  'Job boards': ['LinkedIn Jobs', 'Rozee.pk', 'Indeed'],
  'Posted within': 'Past week',
  'What you offer / your CV summary': 'We are a Flutter agency in Lahore offering dedicated mobile teams.',
  'Ranking method': 'AI ranking (Gemini)',
  'Minimum fit score (1-5)': '3',
  'Find a decision-maker? (clients mode)': 'Yes',
  'Maximum leads': '10',
};

(async () => {
  // 1) Clients mode happy path
  const existing = [{ Mode: 'Clients', 'Job URL': 'https://www.linkedin.com/jobs/view/4000000007', 'Dedupe Key': 'clients|devsinc|flutterdeveloper' }];
  const r1 = await runWorkflow({ form: baseForm, existingRows: existing, mocks: { firecrawl: firecrawlMock, gemini: geminiMock, contact: contactMock } });
  const leads = r1.appended.Leads;
  const log = r1.appended['Run Log'][0];
  console.log('Clients run:', log.Status, `saved=${log.Saved}`, `skipped=${log.Skipped}`, `attempts=${log.Attempts}`, r1.calls);
  assert.strictEqual(log.Status, 'target_reached');
  assert.strictEqual(leads.length, 10);
  assert.ok(leads.every((l) => Number(l['Fit Score']) >= 3), 'all saved leads meet min score');
  assert.ok(!leads.some((l) => l['Job URL'] === 'https://www.linkedin.com/jobs/view/4000000007'), 'existing URL skipped');
  assert.ok(!leads.some((l) => /indeed\.com\/q-/.test(l['Job URL'])), 'listing pages skipped');
  assert.strictEqual(new Set(leads.map((l) => l['Job URL'])).size, leads.length, 'no duplicate URLs');
  const keys = leads.map((l) => l['Dedupe Key']).filter(Boolean);
  assert.strictEqual(new Set(keys).size, keys.length, 'no duplicate company+role');
  assert.ok(!keys.includes('clients|devsinc|flutterdeveloper'), 'existing dedupe key skipped');
  assert.ok(leads.some((l) => l['Contact LinkedIn'].includes('/in/ali-')), 'contact found');
  assert.ok(!leads.some((l) => l['Contact LinkedIn'].includes('random-person')), 'wrong-company contact rejected');
  console.log('Sample lead:', JSON.stringify(leads[0], null, 2));

  // 2) Jobs mode: no contact lookup
  const r2 = await runWorkflow({ form: { ...baseForm, Mode: 'Find jobs for me', 'Maximum leads': '10' }, existingRows: existing, mocks: { firecrawl: firecrawlMock, gemini: geminiMock, contact: contactMock } });
  console.log('Jobs run:', r2.appended['Run Log'][0].Status, `saved=${r2.appended.Leads.length}`, r2.calls);
  assert.strictEqual(r2.calls.contact, 0);
  assert.ok(r2.appended.Leads.every((l) => l.Mode === 'Jobs' && l.Status === 'To apply'));

  // 3) Firecrawl out of credits -> stop after 3 API errors
  const r3 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { firecrawl: () => ({ success: false, error: 'Insufficient credits' }), gemini: geminiMock, contact: contactMock } });
  const l3 = r3.appended['Run Log'][0];
  console.log('API error run:', l3.Status, `attempts=${l3.Attempts}`, l3['Last Error']);
  assert.strictEqual(l3.Status, 'api_error');
  assert.strictEqual(r3.calls.firecrawl, 3);

  // 4) Gemini down -> leads still saved, unscored
  const r4 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { firecrawl: firecrawlMock, gemini: () => ({ error: { code: 403, message: 'API key not valid' } }), contact: contactMock } });
  console.log('AI error run:', r4.appended['Run Log'][0].Status, `aiErrors=${r4.appended['Run Log'][0]['AI Errors']}`);
  assert.ok(r4.appended.Leads.every((l) => l['Fit Reason'].startsWith('Not scored')));

  // 5) Empty sheet + nothing found -> stops at retry limit, no crash
  const r5 = await runWorkflow({ form: baseForm, existingRows: [], mocks: { firecrawl: () => ({ success: true, data: { web: [] } }), gemini: geminiMock, contact: contactMock } });
  console.log('Empty run:', r5.appended['Run Log'][0].Status, `attempts=${r5.appended['Run Log'][0].Attempts}`);
  assert.strictEqual(r5.appended['Run Log'][0].Status, 'retry_limit_reached');

  // 6) Keyword ranking: no Gemini calls, scores come from keyword overlap
  const kwMocks = { firecrawl: firecrawlMock, gemini: () => { throw new Error('Gemini must not be called'); }, contact: contactMock };
  const r6 = await runWorkflow({ form: { ...baseForm, 'Ranking method': 'Keyword ranking (no AI)' }, existingRows: existing, mocks: kwMocks });
  const l6 = r6.appended['Run Log'][0];
  console.log('Keyword run:', l6.Status, `saved=${l6.Saved}`, `ranking=${l6.Ranking}`, r6.calls);
  assert.strictEqual(r6.calls.gemini, 0);
  assert.strictEqual(l6.Ranking, 'Keyword');
  assert.ok(r6.appended.Leads.every((l) => Number(l['Fit Score']) >= 3 && l['Fit Reason'].startsWith('Keyword score')));
  console.log('Keyword sample reason:', r6.appended.Leads[0]['Fit Reason']);

  // 7) No ranking: save every valid, non-duplicate posting
  const r7 = await runWorkflow({ form: { ...baseForm, 'Ranking method': 'No ranking (save all)', 'Find a decision-maker? (clients mode)': 'No' }, existingRows: existing, mocks: kwMocks });
  const l7 = r7.appended['Run Log'][0];
  console.log('No-ranking run:', l7.Status, `saved=${l7.Saved}`, `attempts=${l7.Attempts}`, r7.calls);
  assert.strictEqual(r7.calls.gemini, 0);
  assert.strictEqual(r7.calls.contact, 0);
  assert.ok(r7.appended.Leads.every((l) => l['Fit Score'] === '' && l['Fit Reason'] === 'Not ranked'));
  assert.ok(!r7.appended.Leads.some((l) => l['Dedupe Key'] === 'clients|devsinc|flutterdeveloper'));

  console.log('\nAll checks passed.');
})().catch((e) => { console.error(e); process.exit(1); });
