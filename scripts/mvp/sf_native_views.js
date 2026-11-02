// Captures Salesforce's own DRO screens for one order: the Decomposition Viewer (Order > Fulfillment Plan tab)
// and the full orchestration plan (all steps). Same sign-in and privacy rules as sf_evidence.js: the sf CLI one-time
// URL is never printed, logged or saved; headless has no URL bar; global header and user names are blurred; images are
// cropped to the component, so no tabs, session or user details appear.
// Usage (repo root): node scripts/mvp/sf_native_views.js <outDir> <orderId> <planId>
const { chromium } = require(require('path').join(__dirname, '..', '..', 'web', 'node_modules', 'playwright-core'));
const { execFileSync } = require('child_process');
const path = require('path');
const [out, orderId, planId] = process.argv.slice(2);
const APP = '/lightning/app/standard__CommunicationsSalesConsole';   // the app whose Order page carries the Decomposition Viewer
function oneTimeUrl(p) {
  let raw; try { raw = execFileSync('sf', ['org', 'open', '--url-only', '-p', p, '--target-org', process.env.SF_ALIAS || 'sfcomms', '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }); }
  catch (e) { throw new Error('sf org open failed (exit ' + e.status + ')'); }
  return JSON.parse(raw).result.url;
}
const HIDE = `.slds-global-header_container, .oneGlobalNav, .branding-userProfile-button, .oneUserProfileCardTrigger { filter: blur(9px) !important; }
  .oneUtilityBar, .utilitybar, .slds-utility-bar_container { display: none !important; }
  a[href*="/005"], a[href*="/r/User/"], .forceOwnerLookup { filter: blur(7px) !important; }`;
const wait = (pg, ms) => pg.waitForTimeout(ms);
async function shot(page, loc, file, pad = 8) {
  await page.addStyleTag({ content: HIDE });
  const b = await loc.boundingBox(); if (!b) throw new Error('component not found for ' + path.basename(file));
  await page.screenshot({ path: file, clip: { x: Math.max(0, b.x - pad), y: Math.max(0, b.y - pad), width: b.width + 2 * pad, height: b.height + 2 * pad } });
  console.log('saved ' + file + ' ' + Math.round(b.width) + 'x' + Math.round(b.height));
}
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(oneTimeUrl(APP), { waitUntil: 'domcontentloaded', timeout: 90000 }); await wait(page, 9000);
  const origin = new URL(page.url()).origin;
  // 1) Decomposition Viewer
  await page.goto(origin + '/lightning/r/Order/' + orderId + '/view', { waitUntil: 'domcontentloaded', timeout: 90000 }); await wait(page, 10000);
  await page.locator('a[role="tab"]:has-text("Fulfillment Plan")').last().click(); await wait(page, 8000);
  const dv = page.locator('runtime_industries_dfo_decomp-decomposition-viewer, [class*="decomposition"]').filter({ hasText: 'Decomposed Line Items' }).last();
  const exp = dv.locator('button:has(lightning-primitive-icon), button[title*="Expand" i], .slds-button_icon').first();
  for (const sel of ['button[aria-label*="Expand" i]', 'button[title*="Expand" i]', 'lightning-button-icon[class*="expand"] button']) {
    const b = dv.locator(sel).first(); if (await b.isVisible().catch(() => false)) { await b.click(); await wait(page, 3000); break; }
  }
  await shot(page, dv, path.join(out, 'sf-decomposition.png'));
  // 2) Orchestration plan, all steps: wide viewport, then the viewer's own zoom-out until the last step is on screen
  await page.setViewportSize({ width: +(process.env.PLAN_W || 2400), height: 1000 });
  await page.goto(origin + '/lightning/r/FulfillmentPlan/' + planId + '/view', { waitUntil: 'domcontentloaded', timeout: 90000 }); await wait(page, 12000);
  const cardsX = () => page.locator('svg[data-key="toggle_panel_right"]').evaluateAll((xs) => xs.map((x) => x.getBoundingClientRect().right));
  const vw = page.viewportSize().width;
  for (let k = 0; k < 6; k++) {   // the plan viewer's own Zoom Out until every step card is on screen
    const xs = await cardsX(); console.log('step cards ' + xs.length + ', last right edge ' + Math.round(Math.max(...xs)));
    if (xs.length && Math.max(...xs) < vw - 40) break;
    await page.locator('svg[data-key="zoomout"]').first().click(); await wait(page, 1500);
  }
  const plan = page.locator('.slds-card, article, section').filter({ hasText: 'Plan Status' }).last();
  await shot(page, plan, path.join(out, 'sf-plan-raw.png'));
  await browser.close();
})().catch((e) => { console.error(String(e.message || e).replace(/https?:\/\/\S+/g, '[url]')); process.exit(1); });
