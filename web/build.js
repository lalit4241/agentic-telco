// Build web/dist/index.html: one offline file behind a client-side AES-256-GCM password gate (ADR-005).
// Password: $TF_DEMO_PASSWORD or the git-ignored ../.demo-password. It is never written to the output.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const R = (...p) => path.join(__dirname, ...p);
const src = (f) => fs.readFileSync(R('src', f), 'utf8');
const pwFile = R('..', '.demo-password');
const pw = process.env.TF_DEMO_PASSWORD || (fs.existsSync(pwFile) ? fs.readFileSync(pwFile, 'utf8').trim() : '');
if (!pw) { console.error('Set TF_DEMO_PASSWORD or create .demo-password (git-ignored) before building.'); process.exit(1); }
const recFile = process.env.ZG_RECORDING || R('..', 'recordings', JSON.parse(fs.readFileSync(R('..', 'recordings', 'latest.json'), 'utf8')).file);
const rec = JSON.parse(fs.readFileSync(recFile, 'utf8'));

// --- trim the recording to what the UI shows (bodies truncated, span attributes dropped, host names removed)
const cut = (v, n = 1200) => { const s = JSON.stringify(v); return s && s.length > n ? s.slice(0, n) + '…' : v; };
const scrub = (s) => JSON.parse(JSON.stringify(s).replace(/zg-l5-worker-[A-Za-z0-9.-]+?-(\d+)"/g, 'zg-l5-worker-$1"'));
const journeys = rec.journeys.map((j) => scrub({
  scenario: j.scenario, title: j.title, story: j.story, runId: j.runId, crash: j.crash, guardrails: j.guardrails,
  run: j.run, saga: j.saga, sagaSteps: j.sagaSteps, events: j.events.map((e) => ({ seq: e.seq, at: e.at, subject: e.subject, body: { source: e.body.source } })),
  inference: j.inference, decisions: j.decisions, process: j.process,
  calls: j.calls.map((c) => ({ seq: c.seq, at: c.at, caller: c.caller, callee: c.callee, method: c.method, path: c.path, status: c.status, api: c.api,
    layer: c.layer, oda_block: c.oda_block, owner: c.owner, runtime: c.runtime, request: cut(c.request), response: cut(c.response) })),
  spans: (j.spans || []).length,
}));

// --- per-layer coverage: Salesforce columns copied exactly from "Zero Gravity on Salesforce – Demos v2", slide 4
const coverage = [
  { layer: 'L1', name: 'Intent & Experience', sf: 'Agentforce, Voice, Contact Center', fit: 'Fit', demo: 'D1 D2 D3', ours: 'TMF921 intent API (our layer – no Salesforce support), replay UI, read-only GraphQL BFF' },
  { layer: 'L2', name: 'Agent Mesh', sf: 'Agentforce, MuleSoft Agent Fabric', fit: 'Partial', demo: 'D2', ours: 'LangGraph care agent, MCP tools, A2A network agent; models only via the inference gateway' },
  { layer: 'L3', name: 'Data Foundations', sf: 'Data 360, zero copy', fit: 'Partial', demo: 'D1 D2', ours: 'PostgreSQL + pgvector data products; TMF688 events on Apache Kafka' },
  { layer: 'L4', name: 'Enterprise Context', sf: 'Data 360, Tableau Semantics', fit: 'Partial / Gap', demo: 'D1 (external policy)', ours: 'Ours: OPA policy service (credit, consent, network safety, AI guardrails, model allow-list); rules change with zero Salesforce changes' },
  { layer: 'L5', name: 'Deterministic Execution', sf: 'Flow, MuleSoft, Agent Script', fit: 'Partial', demo: 'D1 D2 D3', ours: 'Operaton BPMN saga: OPA gate before every SoR write, explicit Policy blocked path, compensation, idempotent workers' },
  { layer: 'L6', name: 'Agent-Ready SoRs', sf: 'Comms Cloud EPC, CPQ, OM', fit: 'Partial', demo: 'D1', ours: 'Salesforce org is the SoR: OOTB TMF629/632/637 + sObject REST first; custom TMF APIs on Salesforce (Apex) for TMF620/648/622; TMF679 tried natively with labelled fallback; OSS mocked' },
  { layer: 'L7', name: 'Digital Core', sf: 'Hyperforce; estate outside Salesforce', fit: 'Partial', demo: '—', ours: 'Ours: one-command runtime; hosts the inference gateway (LiteLLM MIT core → Ollama/vLLM)' },
  { layer: 'L8', name: 'Observability & Governance', sf: 'Agent Health Monitoring, Trust Layer', fit: 'Partial', demo: 'D1 D2 D3', ours: 'OpenTelemetry spans, API-call ledger tagged by ODA block/owner, policy decision log, inference metering' },
];
const coverageGaps = 'TMF921 (no Salesforce support found)  ·  TMF620 still v4  ·  no ODA Component conformance  ·  AI Control Plane on roadmap (~Feb 2027)';

const DATA = scrub({ recordedAt: rec.recordedAt, date: rec.date, label: rec.label, stack: rec.stack, bpmn: rec.bpmn, apis: rec.apis, guardrails: rec.guardrails,
  inferenceGovernance: rec.inferenceGovernance, policyHistory: rec.policyHistory, journeys, coverage, coverageGaps, bom: JSON.parse(src('bom.json')) });

const viewer = fs.readFileSync(R('node_modules', 'bpmn-js', 'dist', 'bpmn-navigated-viewer.production.min.js'), 'utf8');
const bcss = ['diagram-js.css', 'bpmn-js.css'].map((f) => fs.readFileSync(R('node_modules', 'bpmn-js', 'dist', 'assets', f), 'utf8')).join('\n');
const js = 'window.ZG_DATA=' + JSON.stringify(DATA) + ';\n' + viewer + '\n;\n' + src('app.js');
const mark = (k) => src('mark.svg').replace(/id="g"/, `id="g${k}"`).replace(/url\(#g\)/, `url(#g${k})`);
const appHtml = '<style>' + bcss + '</style>' + src('app.template.html').replace('/*MARK*/', () => mark(2));

const salt = crypto.randomBytes(16), iv = crypto.randomBytes(12), iter = 250000, hsalt = crypto.randomBytes(16).toString('hex');
const key = crypto.pbkdf2Sync(pw, salt, iter, 32, 'sha256');
const c = crypto.createCipheriv('aes-256-gcm', key, iv);
const ct = Buffer.concat([c.update(JSON.stringify({ html: appHtml, js }), 'utf8'), c.final(), c.getAuthTag()]);
const payload = { v: 1, iter, salt: salt.toString('base64'), iv: iv.toString('base64'), hsalt, hash: crypto.createHash('sha256').update(hsalt + pw).digest('hex'), ct: ct.toString('base64') };
const gate = src('gate.js').replace('/*PAYLOAD*/null', () => JSON.stringify(payload)).replace(/<\/script/gi, '<\\/script');
const fav = 'data:image/svg+xml,' + encodeURIComponent(src('mark.svg').trim());
const html = src('index.template.html').replace('/*CSS*/', () => src('styles.css')).replace('/*FAVICON*/', fav).replace('/*MARK*/', () => mark(1)).replace('/*GATE*/', () => gate);
// The password must never be stored in the page. If it also appears in the visible page text (e.g. it equals the
// product name) it is guessable: warn loudly, but the leak check below is about the secret-bearing parts.
// The encrypted payload and gate code must never contain the password (the rest of the page is the public template).
if (gate.includes(pw)) { console.error('Refusing to write: password found in output'); process.exit(1); }
if (html.includes(pw)) console.warn('WARNING: the password appears in the public page text, so it is guessable. Use a long random password before sharing.');
if (pw.length < 16) console.warn('WARNING: password shorter than 16 characters. Client-side encryption can be attacked offline; use a long random password and rotate it after events (ADR-005).');
const dataStr = JSON.stringify(DATA), secFile = R('..', '.data', 'secrets.env');
const secrets = fs.existsSync(secFile) ? fs.readFileSync(secFile, 'utf8').split('\n').filter((l) => /PASSWORD|KEY/.test(l)).map((l) => l.split('=').slice(1).join('=').trim()).filter((v) => v.length >= 8) : [];
if (/ZG_OPERATON_|LITELLM_MASTER_KEY|\bsk-[A-Za-z0-9]{16,}/.test(dataStr) || secrets.some((v) => dataStr.includes(v))) { console.error('Refusing to write: secret found in recording'); process.exit(1); }
fs.mkdirSync(R('dist'), { recursive: true });
fs.writeFileSync(R('dist', 'index.html'), html);
console.log('web/dist/index.html', (html.length / 1024).toFixed(0) + ' KB (app + recording encrypted, AES-256-GCM, PBKDF2-SHA256 ' + iter + ') from ' + path.basename(recFile));
