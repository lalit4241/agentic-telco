// MVP headless e2e of web/dist/index.html (playwright-core + system Chrome). Replays the four recorded runs across the three views.
// SHOTS=dir writes 1440x900 preview screenshots. Results go to test/e2e-results.json.
const { chromium } = require('playwright-core');
const path = require('path'), fs = require('fs');
const ROOT = path.join(__dirname, '..', '..');
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const FILE = path.join(__dirname, '..', 'dist', 'index.html');
const PW = process.env.TF_DEMO_PASSWORD || fs.readFileSync(path.join(ROOT, '.demo-password'), 'utf8').trim();
const SHOTS = process.env.SHOTS;
const FOOT = 'Concept demo by Lalit Chauhan · not an official Salesforce product';
const UI = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'mvp', 'ui-copy.json'), 'utf8'));
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: detail || '' }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' — ' + detail : '')); };
(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
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
  check('wrong password refused', await page.isVisible('#gate-form') && !(await page.$('.tabs')));
  await page.fill('#gate-pw', PW); await page.click('#gate-btn');
  await page.waitForSelector('.tabs', { timeout: 30000 });
  check('right password unlocks', !(await page.isVisible('#gate-form').catch(() => false)));
  const head = await page.textContent('header');
  check('title and heading', head.includes('Agent upgrades a Business Customer Service (B2B), on existing systems') && /AGENTICTELCO MVP · BASED ON ZERO GRAVITY ARCHITECTURE/i.test(head));
  const tabs = await page.$$eval('.tabs button', (a) => a.map((b) => b.textContent));
  check('three tabs, business first, each with its question', tabs.length === 3 && tabs[0].includes('Business View') && tabs[1].includes('Architect View') && tabs[2].includes('Dev View') && tabs.every((t, i) => t.includes(UI.tabs[i].subtitle)), tabs.join(' | '));
  check('Business View is the default', await page.isVisible('#v-business') && !(await page.isVisible('#v-cio')));
  check('4 journeys', (await page.$$('.case')).length === 4);
  check('footer, no hosting wording, no model names, no certification claims', await page.evaluate((F) => { const t = document.body.innerText; return t.includes(F) && !/hosting|demo host|docker|ollama|qwen|certified|conformant/i.test(t); }, FOOT));
  check('no "native Salesforce API" anywhere', !/native Salesforce API/.test(await page.content()));
  const end = async () => { await page.click('#b-end'); await page.waitForTimeout(400); };
  const chev = () => page.$$eval('#chev .cv', (a) => a.map((x) => x.className.replace('cv ', '').trim()));
  const chat = () => page.textContent('#chat');
  const bizText = () => page.evaluate(() => document.getElementById('v-business').innerText);
  const scrollTo = (sel) => page.evaluate((q) => { const e = document.querySelector(q); window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 70); }, sel);
  const tab = async (t) => { await page.click(`.tabs button[data-tab="${t}"]`); await page.waitForTimeout(300); };

  // ---- 1. Business View: happy path
  await page.click('.case[data-case="happy"]');
  check('modebar says recorded run', /recorded run/i.test(await page.textContent('#modebar')));
  await page.selectOption('#spd', '4'); await page.waitForTimeout(3500); await shot('1-business-happy-start.png');
  check('play advances the step bar', (await chev()).some((x) => /now|done/.test(x)));
  // while playing, the Architect View lights the layers in use
  await tab('cio'); await page.waitForTimeout(500);
  check('Architect View lights layers during the replay', (await page.$$('#dsvg .dn.on')).length >= 2, String((await page.$$('#dsvg .dn.on')).length));
  await tab('business');
  await end();
  let c = await chev(), t = await chat(), b = await bizText();
  check('happy: step bar Asks..Live, all done, Live green', c.length === 6 && c[5].includes('live') && !c.some((x) => /blocked|delay/.test(x)), c.join(','));
  check('happy: step labels', (await page.$$eval('#chev .cv b', (a) => a.map((x) => x.textContent))).join(',') === 'Asks,Checks,Recommends,Agrees,Ordered,Live');
  check('happy: Sam Taylor, Operations Director', /Sam Taylor/.test(b) && /Operations Director/.test(b));
  check('happy: chat has Fibre 900 £45, contract end kept, live', /Fibre 900/.test(t) && /£45/.test(t) && /28 August 2027/.test(t) && /live/i.test(t));
  const out = await page.textContent('#outcome');
  check('happy: outcome card Fibre 900, £45, 28 Aug 2027, order from the recording, live 2 Nov 2026', /Fibre 900 is live/.test(out) && /£45 a month/.test(out) && /28 Aug 2027/.test(out) && out.includes(JSON.parse(fs.readFileSync(path.join(ROOT, 'recordings', 'mvp', 'happy.json'), 'utf8')).state.links.orderNumber) && /2 Nov 2026/.test(out), out);
  check('happy: Business View line "One upgrade, three services, one router swap."', out.includes(UI.business.orchestrationLine) && UI.business.orchestrationLine === 'One upgrade, three services, one router swap.');
  check('happy: KPIs derived from the run', (await page.$$('#kpis .kg div')).length === 4 && /request to live/.test(await page.textContent('#kpis')));
  check('Business View has no layer numbers, APIs or drawers', !/\bL[1-8]\b|TMF\d|API/.test(b) && !(await page.$('#v-business [data-about]')));
  await shot('2-business-happy-end.png');

  // ---- step selection drives the Architect and Dev Views
  await page.click('#chev .cv[data-step="4"]');
  check('selecting a step marks it', (await page.$$('#chev .cv.sel')).length === 1);
  await tab('cio');
  const cio = await page.evaluate(() => document.getElementById('v-cio').innerText);
  check('CIO: headline, 3 cards, 4 messages verbatim', cio.includes(UI.cio.headline) && UI.cio.cards.every((x) => cio.includes(x.title) && cio.includes(x.text)) && UI.cio.messages.every((x) => cio.includes(x.title) && cio.includes(x.text)));
  check('CIO: banner', /Agent proposes.*Policy decides.*Workflow writes/s.test(await page.textContent('#v-cio .banner')) && (await page.textContent('#v-cio .banner')).includes('never writes to a system of record'));
  check('CIO: 5 groups and the Salesforce chip, no facade wording in the diagram', (await page.$$('#dsvg .dg')).length === 5 && /TMF Open API/.test(await page.textContent('#dsvg')) && !/\(Salesforce\)/.test(await page.textContent('#dsvg')) && !/facade/i.test(await page.textContent('#dsvg')));
  check('CIO: older systems, the network and the network order adapter arrow tagged Mocked', (await page.$$('#dsvg .mk')).length === 5);
  check('CIO: a real arrow from Order Management to the network order adapter, legend says simulated inside Salesforce', !!(await page.$('#dsvg path.de[data-e="sfom-oss"]')) && !(await page.$('#dsvg .tgt')) && /simulated inside Salesforce for this demo/.test(await page.textContent('#v-cio .glegend')));
  const tree = await page.textContent('#dtree');
  check('CIO: simple decomposition tree Product → CFS → RFS/Resource with action codes', (await page.$$('#dtree .tree li')).length >= 10 && /Wi-Fi 6 Router\s*modify/.test(tree) && /Fibre Access Line\s*noChange/.test(tree) && /Fibre Broadband service \(CFS\)\s*modify/.test(tree) && /Fibre Access service \(CFS\)\s*noChange/.test(tree) && /Managed Router service \(CFS\)\s*modify/.test(tree) && /Router configuration\s*modify/.test(tree) && !/nativeAction|Amend|UpgradeTo/.test(tree) && /removed\s*delete/.test(tree) && /installed\s*add/.test(tree), tree.slice(0, 160));
  const lit = await page.$$eval('#dsvg .dn.on', (a) => a.map((x) => x.dataset.node));
  check('CIO: "Ordered" lights the workflow, the APIs and Salesforce', ['L5', 'api', 'sf'].every((n) => lit.includes(n)), lit.join(','));
  check('CIO: no Exposed APIs list here', !(await page.$('#v-cio #exposed')));
  await page.click('#cstrip .pill[data-step="1"]'); await page.waitForTimeout(200);
  const lit1 = await page.$$eval('#dsvg .dn.on', (a) => a.map((x) => x.dataset.node));
  check('CIO: "Checks" lights the context and policy layers and the older systems', ['L4', 'billing'].every((n) => lit1.includes(n)), lit1.join(','));
  await page.click('#cstrip .pill[data-step="1"]');   // back to following the replay (end of run: everything lit)
  await page.waitForTimeout(700); await shot('3-cio-diagram.png');
  await page.evaluate(() => window.scrollTo(0, 0));
  check('CIO: diagram caption visible without scrolling at 1440x900', await page.$eval('#dcap', (e) => { const r = e.getBoundingClientRect(); return r.height > 0 && r.bottom <= window.innerHeight; }));
  const msgText = await page.textContent('#v-cio .msgs');
  check('CIO: four messages with the reworded Controls hold and No lock-in', (await page.$$('#v-cio .msgs .mc')).length === 4 && msgText.includes('Authorisation, overdue balance, availability and the customer\'s go-ahead are all checked before any order, never left to the AI.') && msgText.includes('Salesforce and the older systems are reached only through TM Forum Open APIs (TMF-aligned).'));
  await scrollTo('#v-cio .msgs'); await page.waitForTimeout(300); await shot('10-cio-four-messages.png'); await page.evaluate(() => window.scrollTo(0, 0));
  await page.click('#cstrip .pill[data-step="4"]'); await page.waitForTimeout(200);
  // the diagram opens the layer detail
  for (const [node, L, want] of [['L1', 'L1', /intent/i], ['L2', 'L2', /token/i], ['L3', 'L3', /001QH00002La125YAB/], ['L4', 'L4', /policy|authorised/i], ['L5', 'L5', /Operaton|BPMN/i], ['api', 'L6', /TMF Open API[\s\S]*Decomposition[\s\S]*Orchestration plan/], ['L7', 'L7', /900/], ['L8', 'L8', /trace/i]]) {
    await page.click(`#dsvg .dn[data-node="${node}"]`); await page.waitForTimeout(L === 'L5' ? 1200 : 300);
    const d = await page.textContent('#drawer');
    check(`CIO: ${node} opens the ${L} detail with run data`, (await page.isVisible('#drawer.open')) && want.test(d));
    if (L === 'L2') check('L2 detail shows no model or runtime names', !/ollama|qwen|instruct/i.test(d));
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
  }
  const figs = await page.$$('#v-cio figure.ev');
  check('CIO: Salesforce evidence gallery', figs.length >= 6 && (await page.textContent('#gallery h2')) === 'Proof: the real records in Salesforce', String(figs.length));
  await scrollTo('#dtree'); await page.waitForTimeout(300); await shot('11-cio-decomposition-tree.png');
  await scrollTo('#gallery'); await page.waitForTimeout(400); await shot('4-cio-gallery.png');

  // ---- 3. Dev View
  await tab('architect');
  check('architect: step timeline with whole journey and 6 steps', (await page.$$('#atl .as')).length === 7);
  check('architect: selected step carries over (Ordered)', /Ordered/.test(await page.textContent('#atl .as.sel')));
  check('architect: 8 layer sections', (await page.$$('#alay .lsec')).length === 8);
  let al = await page.textContent('#alay');
  check('architect Ordered: policy binding decision, BPMN, TMF order calls', /binding/i.test(al) && !!(await page.$('#alay .lsec[data-layer="L5"] .djs-container')) && /TMF622/.test(al), '');
  await page.waitForTimeout(800);
  await scrollTo('#alay .lsec[data-layer="L5"]'); await shot('6-architect-ordered-workflow-apis.png');
  const callRow = await page.$('#alay .lsec[data-layer="L6"] tr.call:has-text("TMF Open API")');
  await callRow.click(); await page.waitForSelector('#calld.open');
  const cd = await page.textContent('#calld');
  check('call detail: Provided by, TMF tag, request and response', /Provided by: (Salesforce \(out of the box\)|TMF facade within Salesforce \(Apex\))/.test(cd) && /TMF\d{3}/.test(cd) && /Request/.test(cd) && /Response/.test(cd), cd.slice(0, 120));
  check('call detail: redacted (no tokens, session ids, login URLs)', !/access_token|Bearer |sid=|frontdoor|00D[A-Za-z0-9]{12,15}!|my\.salesforce\.com/i.test(cd));
  await page.click('#calld .x');
  await page.click('#atl .as[data-step="1"]'); await page.waitForTimeout(400);
  al = await page.textContent('#alay');
  check('architect Checks: context pack with sources, policy rule and decision', (await page.$$('#alay .lsec[data-layer="L4"] .chip')).length > 5 && /Sources: TMF reads/.test(al) && /allow|deny/i.test(al));
  check('architect Checks: audit entries with matched IDs and xref', /IDs matched across systems/.test(al) && /[0-9a-f]{32}/.test(al) && /001QH00002La125YAB/.test(al));
  check('architect: step spans listed, call rows clickable', (await page.$$('#atl tr.call')).length > 3);
  await page.evaluate(() => { window.scrollTo(0, 0); }); await shot('7-architect-checks-context-policy.png');
  await page.click('#atl .as[data-step="0"]'); await page.waitForTimeout(400);
  check('architect Asks: TMF921 intent shown', /Intent \[TMF921\]/.test(await page.textContent('#alay .lsec[data-layer="L1"]')) || /intent/i.test(await page.textContent('#alay')));
  await page.click('#atl .as[data-step="5"]'); await page.waitForTimeout(400);
  al = await page.textContent('#alay');
  check('architect Live: network change and audit', /900/.test(await page.textContent('#alay .lsec[data-layer="L7"]')) && !(await page.$('#alay .lsec[data-layer="L7"].idle')));
  await scrollTo('#alay .lsec[data-layer="L7"]'); await shot('8-architect-live-network.png');
  const l6 = await page.textContent('#alay .lsec[data-layer="L6"]');
  check('architect Live: Decomposition panel (level, item, action code, why) and Orchestration plan panel', /Decomposition \(Salesforce order orchestration\)/.test(l6) && /LevelItemAction codeWhy/.test(l6) && /Orchestration plan/.test(l6) && /Point of no return/.test(l6) && /acknowledged → inProgress → completed/.test(l6), l6.slice(0, 120));
  check('architect Live: "The TMF641 request and response are simulated inside Salesforce for this demo."', l6.includes('The TMF641 request and response are simulated inside Salesforce for this demo.') && /Network order adapter \(Mocked\)/.test(l6));
  await page.evaluate(() => { const e = [...document.querySelectorAll('#alay .lsec[data-layer="L6"] .sec')].find((x) => /^Decomposition/.test(x.textContent)); window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - 70); });
  await page.waitForTimeout(300); await shot('12-dev-decomposition-plan.png');
  const arch = await page.textContent('#v-architect');
  check('architect: system-of-record line', arch.includes('All system-of-record access is through TM Forum Open APIs exposed by Salesforce; no Salesforce-specific APIs above the systems layer.'));
  check('architect: Exposed APIs (out of the box, facade, stand-ins mocked)', /Exposed APIs \(TMF-aligned\)/.test(arch) && /Provided by: Salesforce \(out of the box\)/.test(arch) && /Provided by: TMF facade within Salesforce \(Apex\)/.test(arch) && /Legacy stand-in \(mocked\)/.test(arch) && (await page.$$('#exposed tr')).length >= 15);
  check('architect: Exposed APIs list the network order adapter (Mocked) with TMF685, TMF639, TMF641, TMF638', /Network order adapter \(Mocked\)/.test(await page.textContent('#exposed')) && ['TMF685', 'TMF639', 'TMF641', 'TMF638'].every((x) => (arch.match(new RegExp(x, 'g')) || []).length >= 1));
  check('architect: ODA/eTOM/SID panel is "conceptual alignment", never certified', /conceptual alignment/.test(arch) && (await page.$$('#oda tr')).length >= 8 && !/certif|conforman/i.test(arch));
  check('architect: 31 glossary terms', (await page.$$('#gl .gt')).length === 31, String((await page.$$('#gl .gt')).length));
  await page.fill('#glf', 'jeopardy'); check('glossary filter', (await page.$$('#gl .gt')).length >= 1 && (await page.$$('#gl .gt')).length < 31);
  await page.fill('#glf', '');
  await scrollTo('#exposed'); await shot('5-architect-exposed-apis.png');

  // ---- other journeys
  await tab('business');
  await page.click('.case[data-case="notauth"]'); await end();
  c = await chev(); t = await chat();
  check('notauth: blocked, points to Sam, no order', c.some((x) => x.includes('blocked')) && /Sam/.test(t) && !c[5].includes('live') && /No order/.test(await page.textContent('#outcome')), c.join(','));
  check('notauth: Alex Reed, not authorised', /Alex Reed/.test(await bizText()));
  await shot('9-business-not-authorised.png');
  await page.click('.case[data-case="overdue"]'); await end();
  c = await chev(); t = await chat();
  check('overdue: blocked, overdue reason only, pay link', c.some((x) => x.includes('blocked')) && /overdue/i.test(t) && /https:\/\/pay\./.test(t) && !/authori[sz]ed contact/i.test(t), c.join(','));
  await tab('architect'); await page.click('#atl .as[data-step="4"]'); await page.waitForTimeout(300);
  check('overdue: architect says the step does not happen', /does not happen in this journey/.test(await page.textContent('#alay')));
  await tab('business');
  await page.click('.case[data-case="delayed"]'); await end();
  c = await chev(); t = await chat();
  check('delayed: Live step says delayed, customer told first', c[5].includes('live') && /2 days late, Sam told first/.test(await page.textContent('#chev .cv[data-step="5"]')), c.join(','));
  check('delayed: Sam told of delay before go-live', t.search(/delay|risk/i) >= 0 && t.search(/delay|risk/i) < t.lastIndexOf('live'));
  check('delayed: order number not shown anywhere', !(await page.evaluate(() => document.body.innerText)).includes('00000171'));
  await tab('architect'); await page.click('#atl .as[data-step="all"]'); await page.waitForTimeout(500);
  check('delayed: order number masked in the architect view', !(await page.evaluate(() => document.body.innerText)).includes('00000171'));
  const banned = /ollama|qwen|local model|local open-weight|consent/i; let seen = [];
  for (const st of ['0', '1', '2', '3', '4', '5', 'all']) { const b = await page.$(`#atl .as[data-step="${st}"]`); if (b) { await b.click(); await page.waitForTimeout(250); } const m = (await page.textContent('#v-architect')).match(banned); if (m) seen.push(st + ':' + m[0]); }
  await tab('cio'); { const m = (await page.textContent('#v-cio')).match(banned); if (m) seen.push('cio:' + m[0]); }
  check('no model names, "local" runtime wording or consent-check claims on screen', seen.length === 0, seen.join(','));
  await tab('business');
  await page.keyboard.press('p'); check('presenter mode toggles', await page.evaluate(() => document.body.classList.contains('presenter')));
  await page.keyboard.press('p');

  // ---- responsive: no horizontal overflow at 1280x800 and 1920x1080 on any view
  for (const [w, h] of [[1280, 800], [1920, 1080]]) {
    await page.setViewportSize({ width: w, height: h });
    for (const tb of ['business', 'cio', 'architect']) {
      await tab(tb);
      const ov = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check(`responsive ${w}x${h}: ${tb} fits the width`, ov <= 0, String(ov));
    }
  }
  check('no console errors', errors.length === 0, errors.join(' | ').slice(0, 300));
  await browser.close();
  fs.writeFileSync(path.join(__dirname, 'e2e-results.json'), JSON.stringify({ at: new Date().toISOString(), results }, null, 1));
  const failed = results.filter((r) => !r.ok).length;
  console.log(`${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
