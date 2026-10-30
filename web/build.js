// AgenticTelco MVP web build.
//   node build.js          -> web/src/mvp/copy.json + web/dist/index.html (password-gated replay of the recorded runs, AES-256-GCM)
//   node build.js --live   -> web/src/mvp/copy.json + web/dist/mvp-live.html (no gate; served by the local gateway, talks to /api/*)
//   node build.js --copy   -> web/src/mvp/copy.json only
// docs/mvp/layer-panels.md is the single source of the layer copy and the glossary (parsed by src/mvp/parse-copy.js).
// The pre-MVP replay is built by build-legacy.js (dist/legacy.html).
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const { parseCopy } = require('./src/mvp/parse-copy.js');
const R = (...p) => path.join(__dirname, ...p), ROOT = R('..');
const rd = (...p) => fs.readFileSync(path.join(...p), 'utf8');
const args = process.argv.slice(2), LIVE = args.includes('--live');

const copy = parseCopy(rd(ROOT, 'docs', 'mvp', 'layer-panels.md'));
if (copy.layers.length !== 8) { console.error('layer-panels.md: expected 8 layers, got ' + copy.layers.length); process.exit(1); }
fs.writeFileSync(R('src', 'mvp', 'copy.json'), JSON.stringify(copy, null, 1) + '\n');
console.log('web/src/mvp/copy.json', copy.layers.length + ' layers,', copy.glossary.length + ' glossary terms');
if (args.includes('--copy')) process.exit(0);

const bpmn = rd(ROOT, 'stack', 'mvp', 'bpmn', 'agentictelco-mvp-upgrade.bpmn');
const rego = rd(ROOT, 'stack', 'mvp', 'policy', 'upgrade.rego');
const viewer = fs.readFileSync(R('node_modules', 'bpmn-js', 'dist', 'bpmn-navigated-viewer.production.min.js'), 'utf8');
const bcss = ['diagram-js.css', 'bpmn-js.css'].map((f) => fs.readFileSync(R('node_modules', 'bpmn-js', 'dist', 'assets', f), 'utf8')).join('\n');
const mark = (k) => rd(R('src', 'mark.svg')).replace(/id="g"/, `id="g${k}"`).replace(/url\(#g\)/, `url(#g${k})`);
const css = bcss + '\n' + rd(R('src', 'mvp', 'mvp.css'));
const fav = 'data:image/svg+xml,' + encodeURIComponent(rd(R('src', 'mark.svg')).trim());
const MODEL = 'Qwen3-4B-Instruct-2507 (local, Ollama)';

// ---- recorded runs (recordings/mvp/<case>.json = final /api/state of a real run; the UI replays it by timestamp)
const cut = (v, n = 1500) => { if (v == null) return v; const s = JSON.stringify(v); return s.length > n ? s.slice(0, n) + '…' : v; };
// Redaction (the gateway already redacts /api/state; this is the second line): no tokens, session ids, login or instance URLs.
const SECRET_KEY = /^(?:(?:access|refresh|id|bearer|api)?_?token|session_?id|sid|(?:set-)?cookie)$|authori[sz]ation|password|secret|frontdoor/i;
function redact(x) {
  if (Array.isArray(x)) return x.map(redact);
  if (x && typeof x === 'object') return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, SECRET_KEY.test(k) ? '[redacted]' : redact(v)]));
  if (typeof x === 'string') return x.replace(/\b00D[A-Za-z0-9]{12,15}![A-Za-z0-9._-]+/g, '[redacted]')
    .replace(/https?:\/\/[A-Za-z0-9.-]+\.(?:my\.)?(?:salesforce|force|cloudforce|salesforce-setup|visualforce)\.com[^\s"']*/g, (u) => (/\/lightning\/r\//.test(u) && !/frontdoor|sid=/.test(u) ? u : '[instance]' + u.replace(/^https?:\/\/[^/]+/, '').split('?')[0]));
  return x;
}
function trim(st) {
  const s = redact(JSON.parse(JSON.stringify(st)));
  s.spans = (s.spans || []).map((x) => ({ ...x, request: cut(x.request), response: cut(x.response) }));
  if (s.network) s.network = { site: s.network.site, exchange: s.network.exchange, fibrePath: s.network.fibrePath, accessPort: { id: (s.network.accessPort || {}).id }, 'x-mocked': true };
  return s;
}
function recordings() {
  const dir = path.join(ROOT, 'recordings', 'mvp'), out = {};
  for (const c of ['happy', 'notauth', 'overdue', 'delayed']) {
    const f = path.join(dir, c + '.json');
    if (!fs.existsSync(f)) { console.error('missing recording ' + f + ' (run scripts/record_mvp.py)'); process.exit(1); }
    const r = JSON.parse(fs.readFileSync(f, 'utf8'));
    out[c] = { case: c, title: r.title, recordedAt: r.recordedAt, label: 'recorded run', state: trim(r.state) };
  }
  return out;
}
// ---- Salesforce evidence gallery: web/src/mvp/evidence/NN-name.(jpg|png), story order; captions.json { "NN-name.jpg": "caption" }
function evidence() {
  const dir = R('src', 'mvp', 'evidence');
  if (!fs.existsSync(dir)) return [];
  const caps = fs.existsSync(path.join(dir, 'captions.json')) ? JSON.parse(rd(path.join(dir, 'captions.json'))) : {};
  return fs.readdirSync(dir).filter((f) => /^\d\d-.*\.(jpe?g|png)$/.test(f)).sort().map((f) => ({
    file: f, caption: caps[f] || '[Caption to come]',
    src: 'data:image/' + (/png$/.test(f) ? 'png' : 'jpeg') + ';base64,' + fs.readFileSync(path.join(dir, f)).toString('base64') }));
}
function leakCheck(str, pw) {
  const secFile = path.join(ROOT, '.data', 'secrets.env');
  const secrets = fs.existsSync(secFile) ? rd(secFile).split('\n').filter((l) => /PASSWORD|KEY|SECRET|TOKEN/.test(l)).map((l) => l.split('=').slice(1).join('=').trim()).filter((v) => v.length >= 8) : [];
  if (pw) secrets.push(pw);
  if (/client_secret|access_token|refresh_token|ZG_OPERATON_|\b00D[A-Za-z0-9]{12,15}![A-Za-z0-9._]{20,}|\bsk-[A-Za-z0-9]{16,}/.test(str) || secrets.some((v) => str.includes(v))) {
    console.error('Refusing to write: secret found in output'); process.exit(1);
  }
}
const appJs = (cfg) => 'window.MVP_CFG=' + JSON.stringify(cfg).replace(/<\/script/gi, '<\\/script') + ';\n' + viewer + '\n;\n' + rd(R('src', 'mvp', 'mvp.js'));
fs.mkdirSync(R('dist'), { recursive: true });

if (LIVE) {
  const js = appJs({ mode: 'live', copy, bpmn, rego, model: MODEL, mark: mark(2), evidence: evidence() });
  const html = rd(R('src', 'mvp', 'index.template.html')).replace('/*CSS*/', () => css).replace('/*FAVICON*/', fav).replace('/*BODYCLASS*/', 'live')
    .replace('/*GATEHTML*/', '').replace('/*SCRIPT*/', () => js.replace(/<\/script/gi, '<\\/script'));
  leakCheck(html);
  fs.writeFileSync(R('dist', 'mvp-live.html'), html);
  console.log('web/dist/mvp-live.html', (html.length / 1024).toFixed(0) + ' KB (live mode, served by the local gateway on :8120)');
  process.exit(0);
}

const pwFile = path.join(ROOT, '.demo-password');
const pw = process.env.TF_DEMO_PASSWORD || (fs.existsSync(pwFile) ? rd(pwFile).trim() : '');
if (!pw) { console.error('Set TF_DEMO_PASSWORD or create .demo-password (git-ignored) before building.'); process.exit(1); }
const recs = recordings();
const js = appJs({ mode: 'recorded', copy, bpmn, rego, model: MODEL, mark: mark(2), recordings: recs, evidence: evidence() });
leakCheck(js);
const appHtml = '<style>' + css + '</style>';
const salt = crypto.randomBytes(16), iv = crypto.randomBytes(12), iter = 250000, hsalt = crypto.randomBytes(16).toString('hex');
const key = crypto.pbkdf2Sync(pw, salt, iter, 32, 'sha256');
const c = crypto.createCipheriv('aes-256-gcm', key, iv);
const ct = Buffer.concat([c.update(JSON.stringify({ html: appHtml, js }), 'utf8'), c.final(), c.getAuthTag()]);
const payload = { v: 1, iter, salt: salt.toString('base64'), iv: iv.toString('base64'), hsalt, hash: crypto.createHash('sha256').update(hsalt + pw).digest('hex'), ct: ct.toString('base64') };
const gate = rd(R('src', 'gate.js')).replace('/*PAYLOAD*/null', () => JSON.stringify(payload)).replace(/<\/script/gi, '<\\/script');
const html = rd(R('src', 'mvp', 'index.template.html')).replace('/*CSS*/', () => rd(R('src', 'mvp', 'mvp.css'))).replace('/*FAVICON*/', fav).replace('/*BODYCLASS*/', 'locked')
  .replace('/*GATEHTML*/', () => rd(R('src', 'mvp', 'gate.html')).replace('/*MARK*/', () => mark(1))).replace('/*SCRIPT*/', () => gate);
if (gate.includes(pw)) { console.error('Refusing to write: password found in output'); process.exit(1); }
if (pw.length < 16) console.warn('WARNING: password shorter than 16 characters; client-side encryption can be attacked offline (ADR-005).');
fs.writeFileSync(R('dist', 'index.html'), html);
console.log('web/dist/index.html', (html.length / 1024).toFixed(0) + ' KB (MVP recorded runs: ' + Object.keys(recs).join(', ') + '; encrypted AES-256-GCM, PBKDF2-SHA256 ' + iter + ')');
