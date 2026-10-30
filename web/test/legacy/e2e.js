// LEGACY headless e2e of web/dist/legacy.html (playwright-core + system Chrome). Writes docs/home.png and docs/journey.png.
const { chromium } = require('playwright-core');
const path = require('path'), fs = require('fs');
const ROOT = path.join(__dirname, '..', '..', '..');
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const URL = process.env.URL || 'file://' + path.join(__dirname, '..', '..', 'dist', 'legacy.html');
const PW = process.env.TF_DEMO_PASSWORD || fs.readFileSync(path.join(ROOT, '.demo-password'), 'utf8').trim();
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: detail || '' }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : '')); };
(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  const raw = fs.readFileSync(path.join(__dirname, '..', '..', 'dist', 'legacy.html'), 'utf8');
  check('source holds no recording content in plaintext', !/David Okafor|Operaton 2\.2\.0|End_PolicyBlocked|tmf-api\/productOrdering/.test(raw));
  check('source holds no Salesforce credential fields', !/client_secret|SF_PASSWORD|access_token/i.test(raw));
  await page.goto(URL);
  check('gate shown first', await page.isVisible('#gate-form'));
  check('footer on gate', (await page.textContent('.gate-foot')).includes('Concept demo by Lalit Chauhan · not an official Salesforce product'));
  await page.fill('#gate-pw', 'wrong-password'); await page.click('#gate-btn');
  await page.waitForFunction(() => document.getElementById('gate-err').textContent.length > 0);
  check('wrong password refused', await page.isVisible('#gate-form') && !(await page.$('.gh')));
  await page.fill('#gate-pw', PW); await page.click('#gate-btn');
  await page.waitForSelector('.gh', { timeout: 20000 });
  check('right password unlocks', !(await page.$('#gate')));
  const bar = await page.textContent('#replay-bar');
  check('replay label with run date', bar.includes('recorded from the open-source stack run on 2026-10-26'), bar.slice(0, 90));
  check('replay bar states L5 engine and stub usage', bar.includes('Operaton 2.2.0') && /inference stub calls: 0/.test(bar));
  check('replay bar names the real org', bar.includes('real Comms Cloud org sfcomms') && /Salesforce REST calls/.test(bar));
  check('app footer', (await page.textContent('.ft')).trim() === 'Concept demo by Lalit Chauhan · not an official Salesforce product');
  check('8 layers + gateway as extension (not a ninth layer)', (await page.$$('.stack .layer')).length === 9 && (await page.textContent('.layer.ext')).includes('not a ninth layer'));
  check('no Salesforce / TM Forum logo images', (await page.$$('img')).length === 0);
  await page.screenshot({ path: path.join(ROOT, 'docs', 'home.png'), fullPage: false });
  // journeys
  await page.click('[data-view="journeys"]');
  const n = (await page.$$('.jlist button')).length;
  check('9 journeys listed', n === 9, String(n));
  const expect = { 0: 'End_Completed', 2: 'End_PolicyBlocked', 3: 'End_Compensated', 7: 'End_Completed' };
  for (let i = 0; i < n; i++) {
    await page.click(`.jlist button[data-i="${i}"]`);
    await page.waitForSelector('#trace tr[data-c]');
    const title = await page.textContent('.jhead h2');
    if (expect[i]) {
      await page.waitForSelector('#bpmn .djs-container svg', { timeout: 15000 });
      const head = await page.textContent('.grid2 .card:nth-child(2) .ch');
      check(`journey ${i} "${title}" BPMN ends at ${expect[i]}`, head.includes(expect[i]));
    }
  }
  // watermark: visible and not overlapped
  await page.click('.jlist button[data-i="3"]');
  await page.waitForSelector('#bpmn .bjs-powered-by');
  await page.$eval('#bpmn', (e) => e.scrollIntoView({ block: 'center' }));
  const wm = await page.evaluate(() => {
    const a = document.querySelector('#bpmn .bjs-powered-by'); const r = a.getBoundingClientRect(); const s = getComputedStyle(a);
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return { w: r.width, h: r.height, vis: s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0, onTop: a === top || a.contains(top), top: top && (top.tagName + '.' + top.className), y: r.top, href: a.href };
  });
  check('bpmn.io watermark visible and not overlapped', wm.w > 0 && wm.h > 0 && wm.vis && wm.onTop && /bpmn\.io/.test(wm.href), JSON.stringify(wm));
  check('compensation tasks highlighted', (await page.$$('#bpmn .zg-comp')).length >= 1);
  const tags = await page.$$eval('#trace .tag', (t) => [...new Set(t.map((x) => x.textContent))]);
  check('trace tags owner/runtime: OOTB + custom TMF API on Salesforce + our layer', tags.includes('our layer') && tags.includes('Salesforce · OOTB') && tags.includes('custom TMF API on Salesforce') && !tags.some((t) => /stand-in/.test(t)), tags.join(' | '));
  await page.check('#f-sf');
  const visible = await page.$$eval('#trace tr[data-o]', (r) => r.filter((x) => x.style.display !== 'none').map((x) => x.dataset.o));
  check('Salesforce-only filter', visible.length > 0 && visible.every((o) => o === 'salesforce'));
  await page.uncheck('#f-sf');
  await page.click('.jlist button[data-i="0"]'); await page.waitForSelector('#bpmn .djs-container svg');
  await page.click('#play'); await page.waitForTimeout(8000);
  check('replay animates steps and trace', (await page.$$('#steps li.lit')).length > 0 && (await page.$$('#trace tr.lit')).length > 0);
  check('inference routing shown', (await page.textContent('#jmain')).includes('litellm → ollama/qwen2.5:0.5b'));
  await page.screenshot({ path: path.join(ROOT, 'docs', 'journey.png'), fullPage: false });
  await page.click('.jlist button[data-i="7"]'); await page.waitForSelector('#trace tr[data-c]');
  check('crash-resume shows exactly 1 service order', /Service orders created: 1\b/.test(await page.textContent('#jmain')));
  await page.click('.jlist button[data-i="8"]'); await page.waitForSelector('#trace tr[data-c]');
  const gtxt = await page.textContent('#jmain');
  check('guardrail journey lists 403 probes', (gtxt.match(/403/g) || []).length >= 4);
  // coverage
  await page.click('[data-view="coverage"]');
  const fits = await page.$$eval('.cov tr td:nth-child(3)', (t) => t.map((x) => x.textContent));
  check('coverage = v2 ratings exactly', JSON.stringify(fits) === JSON.stringify(['Fit', 'Partial', 'Partial', 'Partial / Gap', 'Partial', 'Partial', 'Partial', 'Partial']), fits.join(','));
  const ours = await page.$$eval('.cov tr td:nth-child(5)', (t) => t.map((x) => x.textContent));
  check('L4 and L7 are ours', ours[3].startsWith('Ours:') && ours[6].startsWith('Ours:'));
  // ODA
  await page.click('[data-view="oda"]');
  const oda = await page.textContent('#view');
  check('ODA view: TMF620/622/648 custom TMF API on Salesforce, 629/632/637 OOTB', (oda.match(/custom TMF API on Salesforce/g) || []).length === 3 && (oda.match(/Salesforce · OOTB/g) || []).length >= 3, oda.slice(0, 200));
  check('TMF921 not supported by Salesforce – our layer', /TMF921[\s\S]*Not supported by Salesforce – our layer/.test(oda));
  // guardrails + BOM
  await page.click('[data-view="guardrails"]');
  const g = await page.textContent('#view');
  check('guardrails: US model denied for customer data', g.includes('us-frontier-saas denied'));
  await page.click('[data-view="bom"]');
  const bom = await page.textContent('#view');
  check('BOM: Operaton, Kafka, Strawberry, LiteLLM MIT core', /Operaton[\s\S]*2\.2\.0/.test(bom) && bom.includes('Apache Kafka') && bom.includes('Strawberry') && bom.includes('MIT core only'));
  check('BOM: no Temporal, NATS, Apollo Router, Redpanda, Camunda 8', !/Temporal|NATS|Apollo Router|Redpanda|Camunda 8/.test(bom));
  check('no console errors', errors.length === 0, errors.join(' | ').slice(0, 300));
  // lock
  await page.click('#btn-lock'); await page.waitForSelector('#gate-form');
  check('lock returns to the gate', await page.isVisible('#gate-form'));
  await browser.close();
  fs.writeFileSync(path.join(__dirname, 'e2e-results.json'), JSON.stringify({ at: new Date().toISOString(), results }, null, 1));
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} e2e checks passed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
