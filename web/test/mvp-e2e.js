// MVP headless e2e of web/dist/index.html (playwright-core + system Chrome). Replays the four recorded runs.
// SHOTS=dir writes preview screenshots. Results go to test/e2e-results.json.
const { chromium } = require('playwright-core');
const path = require('path'), fs = require('fs');
const ROOT = path.join(__dirname, '..', '..');
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const FILE = path.join(__dirname, '..', 'dist', 'index.html');
const PW = process.env.TF_DEMO_PASSWORD || fs.readFileSync(path.join(ROOT, '.demo-password'), 'utf8').trim();
const SHOTS = process.env.SHOTS;
const FOOT = 'Concept demo by Lalit Chauhan · not an official Salesforce product';
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: detail || '' }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : '')); };
(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1680, height: 1050 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  const shot = async (n) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, n) }); } };
  const raw = fs.readFileSync(FILE, 'utf8');
  check('source holds no journey content in plaintext', !/Brightwell|Fibre 900|Sam Taylor/.test(raw));
  await page.goto('file://' + FILE);
  check('gate shown first', await page.isVisible('#gate-form'));
  check('footer on gate', (await page.textContent('body')).includes(FOOT));
  await page.fill('#gate-pw', 'wrong-password'); await page.click('#gate-btn');
  await page.waitForFunction(() => document.getElementById('gate-err').textContent.length > 0);
  check('wrong password refused', await page.isVisible('#gate-form') && !(await page.$('.ly')));
  await page.fill('#gate-pw', PW); await page.click('#gate-btn');
  await page.waitForSelector('.ly', { timeout: 30000 });
  check('right password unlocks', !(await page.isVisible('#gate-form').catch(() => false)));
  const head = await page.textContent('header');
  check('title and heading', head.includes('Agent upgrades a Business Customer Service (B2B), on existing systems') && /AGENTICTELCO MVP · BASED ON ZERO GRAVITY ARCHITECTURE/i.test(head));
  const banner = await page.textContent('.banner');
  check('banner', /Agent proposes.*Policy decides.*Workflow writes/s.test(banner) && banner.includes('never writes to a system of record'));
  check('8 layer cards render', (await page.$$('.ly')).length === 8);
  check('L6 chip wording', (await page.textContent('.ly[data-layer="L6"]')).includes('TMF Open APIs (Salesforce)'));
  check('no "native Salesforce API" anywhere', !/native Salesforce API/.test(await page.content()));
  check('4 cases', (await page.$$('.case')).length === 4);
  check('footer and no hosting wording', (await page.textContent('body')).includes(FOOT) && !/hosting|demo host/i.test(await page.textContent('body')));
  const end = async () => { await page.click('#b-end'); await page.waitForTimeout(400); };
  const chev = () => page.$$eval('#chev .cv', (a) => a.map((x) => x.className.replace('cv ', '').trim()));
  const chat = () => page.textContent('#chat');
  // happy: play a little, screenshot mid-run, then end
  await page.click('.case[data-case="happy"]');
  check('modebar says recorded run', /recorded run/i.test(await page.textContent('#modebar')));
  await page.selectOption('#spd', '4'); await page.waitForTimeout(6000); await shot('1-business-view-mid-run.png');
  await end();
  let c = await chev(), t = await chat();
  check('happy: chevrons all done, Live green', c.length === 6 && c[5].includes('live') && !c.some((x) => /blocked|delay/.test(x)), c.join(','));
  check('happy: Fibre 900 £45, contract end kept, live message', /Fibre 900/.test(t) && /£45/.test(t) && /28 August 2027/.test(t) && /live/i.test(t));
  check('happy: layers touched', (await page.$$('.ly.touched')).length >= 7, String((await page.$$('.ly.touched')).length));
  for (const L of ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8']) {
    await page.click(`.ly[data-layer="${L}"]`); await page.waitForTimeout(L === 'L5' ? 1500 : 300);
    const d = await page.textContent('#drawer');
    const want = { L1: /intent/i, L2: /token|model/i, L3: /001QH00002La125YAB/, L4: /policy|authorised/i, L5: /Operaton|BPMN/i, L6: /TMF Open API \(Salesforce\)/, L7: /900/, L8: /trace/i }[L];
    check(`happy: ${L} drawer opens with run data`, (await page.isVisible('#drawer')) && want.test(d));
    if (L === 'L4') { check('L4: context pack with source chips and the rule', (await page.$$('#drawer .chip')).length > 5 && /package agentictelco|deny/.test(d)); await shot('2-L4-context-policy.png'); }
    if (L === 'L5') { check('L5: BPMN diagram rendered with markers', !!(await page.$('#drawer .djs-container')) && (await page.$$('#drawer .djs-element.done, #drawer .done')).length > 0); await shot('3-L5-bpmn.png'); }
    if (L === 'L6') {
      check('L6: record links to Salesforce', (await page.$$('#drawer a[href*="lightning.force.com"]')).length > 0);
      const rows = await page.$$eval('#drawer tr.call', (a) => a.map((r) => r.textContent));
      check('L6 API view: every call shows method, path and TMF tag', rows.length > 8 && rows.every((r) => /(GET|POST|PATCH)/.test(r) && /TMF\d{3}/.test(r) && /\//.test(r)), rows.length + ' rows');
      check('L6 API view: Salesforce calls read "TMF Open API (Salesforce)"', !/facade within Salesforce \(Apex\)|native Salesforce/.test(await page.textContent('#drawer .t.api')) && /TMF Open API \(Salesforce\)/.test(d));
      await shot('8-api-view-L6.png');
      const facadeRow = await page.$('#drawer tr.call:has-text("Create Fibre 900")') || await page.$('#drawer tr.call');
      await facadeRow.click(); await page.waitForSelector('#calld.open');
      let cd = await page.textContent('#calld');
      check('call detail: Provided by, TMF tag, request and response', /Provided by: (Salesforce \(out of the box\)|TMF facade within Salesforce \(Apex\))/.test(cd) && /TMF637 Product Inventory/.test(cd) && /Request/.test(cd) && /Response/.test(cd), cd.slice(0, 120));
      check('call detail: link to the Salesforce record', (await page.$$('#calld a[href*="lightning.force.com/lightning/r/"]')).length === 1);
      check('call detail: redacted (no tokens, session ids, login URLs)', !/access_token|Bearer |sid=|frontdoor|00D[A-Za-z0-9]{12,15}!|my\.salesforce\.com/i.test(cd));
      await shot('9-api-call-detail.png');
      await page.click('#calld .x');
      const native = await page.$('#drawer tr.call:has-text("connect/comms")');
      if (native) { await native.click(); await page.waitForSelector('#calld.open'); check('call detail: out-of-the-box call says so', /Provided by: Salesforce \(out of the box\)/.test(await page.textContent('#calld'))); await page.click('#calld .x'); }
      const legacy = await page.$('#drawer tr.call:has-text("Legacy stand-in")');
      check('legacy calls read "Legacy stand-in (mocked)"', !!legacy);
    }
    if (L === 'L4') {
      const rows = await page.$$eval('#drawer #l4reads tr.call', (a) => a.map((r) => r.textContent));
      check('L4 API view: context reads are TMF calls', rows.length >= 5 && rows.every((r) => /TMF\d{3}/.test(r)), rows.length + ' rows');
      await page.click('#drawer #l4reads tr.call'); await page.waitForSelector('#calld.open'); await shot('10-api-call-detail-L4.png'); await page.click('#calld .x');
    }
    if (L === 'L8') { check('L8: trace and span ids', /[0-9a-f]{32}/.test(d) && /[0-9a-f]{16}/.test(d)); await shot('5-L8-timeline.png'); }
    if (L === 'L7') await shot('4-L7-network.png');
    await page.keyboard.press('Escape'); await page.waitForTimeout(350);   // the drawer covers the layer column; close it before the next card
  }
  await page.keyboard.press('Escape');
  // not authorised
  await page.click('.case[data-case="notauth"]'); await end();
  c = await chev(); t = await chat();
  check('notauth: blocked at Checks, points to Sam', c.some((x) => x.includes('blocked')) && /Sam/.test(t) && !c[5].includes('live'), c.join(','));
  await page.click('.case[data-case="overdue"]'); await end();
  c = await chev(); t = await chat();
  check('overdue: blocked, overdue reason only, pay link', c.some((x) => x.includes('blocked')) && /overdue/i.test(t) && /https:\/\/pay\./.test(t) && !/authori[sz]ed contact/i.test(t), c.join(','));
  await page.click('.case[data-case="delayed"]'); await end();
  c = await chev(); t = await chat();
  check('delayed: delay chevron orange then Live', c[4].includes('delay') && c[5].includes('live'), c.join(','));
  check('delayed: Sam told of delay before go-live', t.search(/delay|risk/i) >= 0 && t.search(/delay|risk/i) < t.lastIndexOf('live'));
  await shot('6-delayed-chevrons.png');
  // architecture tab
  await page.click('.tabs button[data-tab="arch"]'); await page.waitForTimeout(300);
  check('architecture: 8 layer cards', (await page.$$('#v-arch .ac')).length === 8);
  check('architecture: 27 glossary terms', (await page.$$('#gl .gt')).length === 27, String((await page.$$('#gl .gt')).length));
  await page.fill('#glf', 'jeopardy'); check('glossary filter', (await page.$$('#gl .gt')).length >= 1 && (await page.$$('#gl .gt')).length < 27);
  await page.fill('#glf', ''); await shot('7-architecture.png');
  const arch = await page.textContent('#v-arch');
  check('architecture: system-of-record line', arch.includes('All system-of-record access is through TM Forum Open APIs exposed by Salesforce; no Salesforce-specific APIs above the systems layer.'));
  check('architecture: Exposed APIs (out of the box, facade, stand-ins mocked)', /Exposed APIs/.test(arch) && /Provided by: Salesforce \(out of the box\)/.test(arch) && /Provided by: TMF facade within Salesforce \(Apex\)/.test(arch) && /Legacy stand-in \(mocked\)/.test(arch) && (await page.$$('#exposed tr')).length >= 15);
  await (await page.$('#exposed')).scrollIntoViewIfNeeded(); await shot('11-exposed-apis.png');
  await page.click('.tabs button[data-tab="evidence"]'); await page.waitForTimeout(500);
  const figs = await page.$$('#v-evidence figure.ev');
  check('Salesforce evidence gallery (story order)', figs.length >= 6, String(figs.length));
  await shot('12-salesforce-evidence.png');
  await page.click('.tabs button[data-tab="demo"]');
  await page.keyboard.press('p'); check('presenter mode toggles', await page.evaluate(() => document.body.classList.contains('presenter')));
  await page.keyboard.press('p');
  check('no console errors', errors.length === 0, errors.join(' | ').slice(0, 300));
  await browser.close();
  fs.writeFileSync(path.join(__dirname, 'e2e-results.json'), JSON.stringify({ at: new Date().toISOString(), results }, null, 1));
  const failed = results.filter((r) => !r.ok).length;
  console.log(`${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
