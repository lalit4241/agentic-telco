// node --test: checks on the built page and its inputs (run `npm run build` first).
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
const D = JSON.parse(app.js.match(/^window\.ZG_DATA=(.*?);\n/s)[1]);
test('payload is AES-256-GCM with PBKDF2 250k and the verifier does not reveal the password', () => {
  assert.strictEqual(payload.iter, 250000);
  assert.notStrictEqual(payload.hash, crypto.createHash('sha256').update(pw).digest('hex'));
  assert.ok(!JSON.stringify(payload).includes(pw));
});
test('wrong password fails authentication', () => { assert.throws(() => decrypt(payload, pw + 'x')); });
test('coverage uses the v2 deck ratings exactly; L4 and L7 are ours', () => {
  assert.deepStrictEqual(D.coverage.map((c) => [c.layer, c.fit, c.demo]), [['L1', 'Fit', 'D1 D2 D3'], ['L2', 'Partial', 'D2'], ['L3', 'Partial', 'D1 D2'], ['L4', 'Partial / Gap', 'D1 (external policy)'], ['L5', 'Partial', 'D1 D2 D3'], ['L6', 'Partial', 'D1'], ['L7', 'Partial', '—'], ['L8', 'Partial', 'D1 D2 D3']]);
  assert.ok(D.coverage[3].ours.startsWith('Ours:') && D.coverage[6].ours.startsWith('Ours:'));
  assert.match(D.coverageGaps, /TMF921 \(no Salesforce support found\).*TMF620 still v4.*no ODA Component conformance.*~Feb 2027/);
});
test('recording label, engine and stub usage', () => {
  assert.match(D.label, /^recorded from the open-source stack run on \d{4}-\d{2}-\d{2}$/);
  assert.match(D.stack.l5Engine, /Operaton 2\.2\.0/);
  assert.strictEqual(D.stack.inferenceStubCalls, 0);
  assert.strictEqual(D.stack.sorMode, 'commscloud');
  assert.strictEqual(D.stack.sor.orgAlias, 'sfcomms');
  assert.ok(D.stack.sor.salesforceRestCalls > 0);
});
test('real-org calls are labelled OOTB or custom TMF API on Salesforce (or our-layer fallback)', () => {
  const rts = new Set();
  for (const j of D.journeys) for (const c of j.calls) if (c.owner === 'salesforce') rts.add(c.runtime);
  assert.ok(rts.has('OOTB') && rts.has('custom TMF API on Salesforce'), [...rts].join('|'));
  for (const r of rts) assert.match(r, /^(OOTB|custom TMF API on Salesforce|our layer \(native TMF679 tried: 400\))$/);
});
test('every API call is tagged with layer, ODA block, owner and runtime', () => {
  for (const j of D.journeys) for (const c of j.calls) for (const k of ['layer', 'oda_block', 'owner', 'runtime']) assert.ok(c[k], `${j.scenario} ${c.path} missing ${k}`);
});
test('BOM is OSI-licensed apart from the Salesforce SoR and lists no rejected components', () => {
  const s = JSON.stringify(D.bom);
  assert.doesNotMatch(s, /Temporal|NATS|Apollo Router|Redpanda|Camunda 8|Restate|BSL|SSPL|enterprise\/ (installed|enabled)/);
  for (const r of D.bom) if (!/Salesforce/.test(r[1])) assert.match(r[3], /MIT|Apache|BSD|PostgreSQL|AGPL|GPL/, r[1]);
});
test('no secrets or host names in the shipped data', () => {
  const s = JSON.stringify(D);
  assert.doesNotMatch(s, /grok-bot-vm|LITELLM_MASTER_KEY|ZG_OPERATON_|client_secret|access_token/);
  const sec = path.join(ROOT, '.data', 'secrets.env');
  if (fs.existsSync(sec)) for (const l of fs.readFileSync(sec, 'utf8').split('\n')) { const v = l.split('=').slice(1).join('=').trim(); if (/PASSWORD|KEY/.test(l) && v.length >= 8) assert.ok(!s.includes(v)); }
});
test('bpmn-js viewer is bundled and the bpmn.io watermark is not hidden by our CSS', () => {
  assert.match(app.js, /bjs-powered-by/);
  assert.doesNotMatch(html + app.html, /bjs-powered-by[^{]*\{[^}]*(display:\s*none|visibility:\s*hidden|opacity:\s*0)/);
});
test('page has the required footer and no logo images', () => {
  assert.ok(html.includes('Concept demo by Lalit Chauhan · not an official Salesforce product'));
  assert.ok(app.html.includes('Concept demo by Lalit Chauhan · not an official Salesforce product'));
  assert.doesNotMatch(html + app.html, /<img/i);
});
