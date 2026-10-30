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
test('recorded mode with 8 layers and 27 glossary terms from docs/mvp/layer-panels.md', () => {
  assert.strictEqual(CFG.mode, 'recorded');
  assert.deepStrictEqual(CFG.copy.layers.map((l) => l.id), ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8']);
  assert.strictEqual(CFG.copy.glossary.length, 27);
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
test('L6 wording, footer, hosting wording, branding', () => {
  const l6 = CFG.copy.layers.find((l) => l.id === 'L6');
  assert.match(JSON.stringify(l6), /Salesforce native APIs plus a thin TMF facade layer within Salesforce/);
  assert.match(app.js, /Salesforce APIs \+ TMF facade \(in Salesforce\)/);
  assert.ok(html.includes(FOOT) && (app.html + app.js).includes(FOOT));
  assert.match(app.js, /Salesforce runs on instance GBR58 \(REPORTED; UK region to be confirmed\)/);
  assert.doesNotMatch(html + app.html + app.js, /<img|LC monogram/i);
});
test('no secrets in the page', () => {
  const s = html + JSON.stringify(app);
  assert.doesNotMatch(s, /client_secret|access_token|refresh_token|ZG_OPERATON_|00D[A-Za-z0-9]{12,15}![A-Za-z0-9._]{20,}|sk-[A-Za-z0-9]{20,}/);
  const sec = path.join(ROOT, '.data', 'secrets.env');
  if (fs.existsSync(sec)) for (const l of fs.readFileSync(sec, 'utf8').split('\n')) { const v = l.split('=').slice(1).join('=').trim(); if (v.length >= 8) assert.ok(!s.includes(v), 'secret value leaked'); }
});
