// node --test: checks on the built MVP page (run `node build.js` first, which needs recordings/mvp/*.json).
const test = require('node:test'), assert = require('node:assert'), fs = require('fs'), path = require('path'), crypto = require('crypto');
const ROOT = path.join(__dirname, '..', '..');
const html = fs.readFileSync(path.join(__dirname, '..', 'dist', 'index.html'), 'utf8');
const pw = process.env.TF_DEMO_PASSWORD || fs.readFileSync(path.join(ROOT, '.demo-password'), 'utf8').trim();
const payload = JSON.parse(html.match(/(\{"v":1,.*?"ct":"[^"]+"\})/s)[1]);
function decrypt(p, password) {
  const key = crypto.pbkdf2Sync(password, Buffer.from(p.salt, 'base64'), p.iter, 32, 'sha256');
  const buf = Buffer.from(p.ct, 'base64'); const d = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(p.iv, 'base64'));
  d.setAuthTag(buf.subarray(buf.length - 16)); return JSON.parse(Buffer.concat([d.update(buf.subarray(0, buf.length - 16)), d.final()]).toString('utf8'));
}
const app = decrypt(payload, pw);
const CFG = JSON.parse(app.js.match(/^window\.MVP_CFG=(.*?);\n/s)[1]);
const FOOT = 'Concept demo by Lalit Chauhan · not an official Salesforce product';

test('payload is AES-256-GCM, PBKDF2 250k; the verifier does not reveal the password; wrong password fails', () => {
  assert.strictEqual(payload.iter, 250000);
  assert.ok(!html.includes(pw) && !JSON.stringify(payload).includes(pw));
  assert.throws(() => decrypt(payload, pw + 'x'));
  assert.doesNotMatch(html, /Brightwell|Fibre 900/, 'business content must only be inside the encrypted payload');
});
test('recorded mode with 8 layers and 31 glossary terms from docs/mvp/layer-panels.md', () => {
  assert.strictEqual(CFG.mode, 'recorded');
  assert.deepStrictEqual(CFG.copy.layers.map((l) => l.id), ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8']);
  assert.strictEqual(CFG.copy.glossary.length, 31);
});
test('the four journeys are recorded runs with the expected outcomes', () => {
  assert.deepStrictEqual(Object.keys(CFG.recordings).sort(), ['delayed', 'happy', 'notauth', 'overdue']);
  for (const [k, r] of Object.entries(CFG.recordings)) {
    assert.strictEqual(r.label, 'recorded run', k);
    assert.ok(r.state.spans.length > 5, k);
    assert.ok(r.state.spans.every((s) => s.trace_id === r.state.conversation.trace_id), k + ' one trace id per run');
  }
  const txt = (k) => CFG.recordings[k].state.messages.map((m) => m.content).join('\n');
  const H = CFG.recordings.happy.state, D = CFG.recordings.delayed.state;
  assert.strictEqual(H.intent.lifecycle_status, 'fulfilled');
  assert.match(txt('happy'), /Fibre 900/); assert.match(txt('happy'), /£45/); assert.match(txt('happy'), /28 August 2027/);
  assert.strictEqual(D.intent.lifecycle_status, 'fulfilled');
  assert.ok(D.jeopardy.length >= 1, 'delayed run raised jeopardy');
  assert.ok(D.messages.findIndex((m) => /delay/i.test(m.content)) < D.messages.findIndex((m) => /live/i.test(m.content) && m.role !== 'user'), 'Sam told about the delay before go-live');
  assert.ok(!CFG.recordings.notauth.state.intent || CFG.recordings.notauth.state.intent.lifecycle_status !== 'fulfilled');
  assert.match(txt('notauth'), /Sam/);
  assert.match(txt('overdue'), /overdue|outstanding/i);
  for (const k of ['notauth', 'overdue']) assert.ok(!CFG.recordings[k].state.links || !CFG.recordings[k].state.links.order, k + ' places no order');
});
test('policy and model come from this build', () => {
  assert.match(CFG.rego, /package agentictelco/);
  assert.match(CFG.rego, /not_authorised/); assert.match(CFG.rego, /overdue_balance/);
  assert.match(CFG.model, /Qwen3-4B/i);
  assert.match(CFG.bpmn, /bpmndi:BPMNDiagram/);
});
test('L6 wording, footer, no hosting wording, branding', () => {
  const l6 = CFG.copy.layers.find((l) => l.id === 'L6');
  assert.match(JSON.stringify(l6), /TM Forum Open APIs exposed by Salesforce: two out of the box, the rest through a thin TMF facade layer within Salesforce/);
  assert.match(app.js, /TMF Open APIs/);
  assert.doesNotMatch(JSON.stringify(CFG.copy) + JSON.stringify(CFG.ui), /TMF Open APIs? \(Salesforce\)/);
  assert.doesNotMatch(app.js, /native Salesforce API/);
  assert.doesNotMatch(app.js.replace(/not (ODA-)?certified( as conformant)?/g, ''), /\b(conformant|certified)\b/i);
  assert.match(app.js, /All system-of-record access is through TM Forum Open APIs exposed by Salesforce; no Salesforce-specific APIs above the systems layer\./);
  assert.ok(html.includes(FOOT) && (app.html + app.js).includes(FOOT));
  assert.doesNotMatch(app.js, /demo host\. Salesforce is a hosted|regional hosting|UK hosting/);
  assert.doesNotMatch(app.js, /Docker|Compose host/);
  assert.doesNotMatch(app.js, /GBR58|UK region to be confirmed/);
  assert.match(app.js, /event bus'/);   // platform line, no hosting mention (LalitC, 30 Oct)
  assert.match(app.js, /TMF facade within Salesforce \(Apex\)/);
  assert.doesNotMatch(app.js, /facade inside Salesforce/);
  assert.doesNotMatch(html + app.html + app.js, /LC monogram/i);
});
test('every Salesforce call in the recordings is a TM Forum Open API (no SOQL, no sObject REST)', () => {
  for (const [k, r] of Object.entries(CFG.recordings)) {
    const l6 = r.state.spans.filter((s) => s.layer === 'L6');
    assert.ok(l6.length > 3, k);
    for (const s of r.state.spans) {
      assert.doesNotMatch(String(s.path || ''), /\/query\b|\/sobjects\b|\/composite\b|\/tooling\//, k + ' ' + s.step);
      assert.doesNotMatch(String(s.runtime || ''), /native Salesforce/, k + ' ' + s.step);
    }
    for (const s of l6) {
      assert.ok(s.method && s.path, k + ' ' + s.step + ' has method and path');
      if (/^Payment link \(mocked\)$/.test(s.step)) { assert.strictEqual(s.runtime, 'Legacy stand-in (mocked)'); continue; }   // the one non-TMF stand-in
      assert.match(String(s.api || ''), /^TMF\d{3} \S/, k + ' ' + s.step + ' has TMF tag and name');
      if (/^\/services\//.test(s.path)) {
        // the chip was renamed to 'TMF Open API'; recordings made before the rename (not re-recorded) keep the old runtime string
        assert.ok(s.runtime === 'TMF Open API' || (k !== 'happy' && s.runtime === 'TMF Open API (Salesforce)'), k + ' ' + s.step + ' ' + s.runtime);
        assert.match(s.path, /^\/services\/apexrest\/agentictelco\/tmf\d{3}\/|^\/services\/data\/v[\d.]+\/connect\/comms\//, k + ' ' + s.step);
        assert.ok(['Salesforce (out of the box)', 'TMF facade within Salesforce (Apex)'].includes((s.attributes || {}).providedBy), k + ' ' + s.step);
      } else if (/^Network order adapter/.test(s.component || '')) {   // calls made by Salesforce order orchestration (mocked adapter)
        assert.match(String(s.runtime), /network order adapter \(Mocked\)$/, k + ' ' + s.step);
        assert.match(s.path, /^\/tmf-api\//, k + ' ' + s.step);
      } else assert.strictEqual(s.runtime, 'Legacy stand-in (mocked)', k + ' ' + s.step);
    }
  }
});
test('Salesforce evidence gallery in story order', () => {
  assert.ok(CFG.evidence.length >= 6, String(CFG.evidence.length));
  assert.deepStrictEqual(CFG.evidence.map((e) => e.file), CFG.evidence.map((e) => e.file).slice().sort());
  assert.ok(CFG.evidence.every((e) => /^data:image\//.test(e.src) && e.caption));
});
test('evidence gallery tells the recorded happy-path story (same order, numbered 01..N)', () => {
  const H = CFG.recordings.happy.state, num = H.links.orderNumber, ext = H.state.orderExternalId;
  assert.match(num, /^\d{8}$/);
  CFG.evidence.forEach((e, i) => assert.ok(e.file.startsWith(String(i + 1).padStart(2, '0') + '-'), e.file));
  const cited = CFG.evidence.flatMap((e) => (e.caption.match(/order \d{8}/gi) || []).map((m) => m.slice(-8)).concat((e.file.match(/order-(\d{8})/) || []).slice(1)));
  assert.ok(cited.length >= 1 && cited.every((n) => n === num), cited.join(',') + ' vs ' + num);
  assert.ok(!CFG.evidence.some((e) => /MVP-[0-9A-F]{8}/.test(e.caption) && !e.caption.includes(ext)));
});
test('Tab 3 (How it\'s built) says Assetisation done (TMF637); no raw platform status or asset-step wording in the demo UI or recordings', () => {
  assert.doesNotMatch(html + JSON.stringify(app), /AssetizationFailed|Platform order status|Built-in asset step|no assetization step/);
  assert.strictEqual(CFG.ui.diagram.decomposition.assetStep, 'Assetisation done (TMF637)');
  assert.doesNotMatch(html, /PI\.routeLabel|custom step in the Salesforce plan|built-in asset step|Custom Assetize Order flow/i, 'the Dev View label stays neutral');
});
test('no secrets in the page', () => {
  const s = html + JSON.stringify(app);
  assert.doesNotMatch(s, /client_secret|access_token|refresh_token|ZG_OPERATON_|00D[A-Za-z0-9]{12,15}![A-Za-z0-9._]{20,}|sk-[A-Za-z0-9]{20,}/);
  const sec = path.join(ROOT, '.data', 'secrets.env');
  if (fs.existsSync(sec)) for (const l of fs.readFileSync(sec, 'utf8').split('\n')) { const v = l.split('=').slice(1).join('=').trim(); if (v.length >= 8) assert.ok(!s.includes(v), 'secret value leaked'); }
});
test('three audience views, all their copy in one object (ui-copy.json)', () => {
  const UI = CFG.ui;
  assert.deepStrictEqual(UI.tabs.map((t) => t.label), ['What changes for the business', 'How it fits', "How it's built"]);
  assert.deepStrictEqual(UI.tabs.map((t) => t.subtitle), ['An agent handles the upgrade end to end, and policy and workflow keep control', 'On the estate you already have, through TM Forum Open APIs', 'Every call, action code and record, step by step']);
  assert.strictEqual(UI.cio.headline, 'Agentic change, on the estate you already have.');
  assert.deepStrictEqual(UI.cio.cards.map((c) => c.title), ['Agent proposes', 'Policy decides', 'Workflow writes']);
  assert.deepStrictEqual(UI.cio.messages.map((c) => c.title), ['Nothing ripped out', 'No lock-in', 'Controls hold', 'Every step evidenced']);
  assert.deepStrictEqual(UI.diagram.groups.map((g) => g.title), ['Understand', 'Know', 'Act', 'Connect', 'Prove']);
  assert.strictEqual(UI.cio.galleryHeading, 'Proof: the real records in Salesforce');
  assert.deepStrictEqual(UI.business.steps.map((s) => s.label), ['Asks', 'Checks', 'Recommends', 'Agrees', 'Ordered', 'Live']);
  assert.strictEqual(UI.diagram.chips.sf, 'TMF Open API');
  assert.strictEqual(UI.diagram.chips.facade, undefined);   // the picture shows no facade chip; tab 3 keeps the detail
  assert.match(UI.architect.mappingHeading, /conceptual alignment/);
  assert.doesNotMatch(JSON.stringify(UI), /certif|conforman|Salesforce APIs|sObject|hosting|Docker|Ollama|Qwen/i);
});
test('no model names on screen and the delayed order number is masked', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'src', 'mvp', 'mvp.js'), 'utf8');
  assert.doesNotMatch(src.replace(/\/ollama\|qwen[^/]*\/i|\/ollama\/i|\(Ollama\|Qwen\[[^)]*\)|via Ollama/g, ''), /Ollama|Qwen/i);
  assert.doesNotMatch(JSON.stringify(CFG.copy.layers), /Ollama|Qwen|local model/i, 'panel copy names no model or local runtime');
  assert.doesNotMatch(JSON.stringify(CFG.ui), /consent|local model/i);
  assert.ok(CFG.ui.architect.mapping.some((r) => r[3] === 'Intent (TMF921)'));
  assert.match(src, /function rtName/); assert.match(src, /function maskNum/);
  const D = CFG.recordings.delayed.state; assert.ok(JSON.stringify(D).includes(D.links.orderNumber), 'delayed number is in the data, so the UI must mask it');
});
