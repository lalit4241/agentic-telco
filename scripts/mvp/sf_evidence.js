// Salesforce evidence screenshots for the MVP demo (Lightning record pages, story order).
// Login: the sf CLI's one-time URL (`sf org open --url-only`), opened in headless Chrome. The URL is never printed, logged or saved.
// Privacy: the global header (search, user menu), user names (owner / created by / modified by) are blurred; headless has no URL bar.
// Usage (repo root): node scripts/mvp/sf_evidence.js <outDir> <name>=<lightning path> [<name>=<path> ...]
const { chromium } = require(require('path').join(__dirname, '..', '..', 'web', 'node_modules', 'playwright-core'));
const { execFileSync } = require('child_process');
const fs = require('fs'), path = require('path');
const [out, ...jobs] = process.argv.slice(2);
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
function oneTimeUrl(p) {
  let raw;
  try { raw = execFileSync('sf', ['org', 'open', '--url-only', '-p', p, '--target-org', process.env.SF_ALIAS || 'sfcomms', '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }); }
  catch (e) { throw new Error('sf org open failed (exit ' + e.status + ')'); }
  const u = JSON.parse(raw).result.url; if (!/^https:\/\//.test(u)) throw new Error('no URL from sf org open'); return u;
}
const BLUR = `
  .slds-global-header_container, .oneGlobalNav, header#oneHeader .slds-global-header, .branding-userProfile-button, .oneUserProfileCardTrigger { filter: blur(9px) !important; }
  a[href*="/lightning/r/005"], a[href*="/005"], force-owner-lookup, force-lookup a[href*="/User/"], a[href*="/r/User/"], .forceOwnerLookup,
  records-record-layout-item[field-label="Created By"] .slds-form-element__control, records-record-layout-item[field-label="Last Modified By"] .slds-form-element__control,
  records-record-layout-item[field-label="Owner"] .slds-form-element__control, records-record-layout-item[field-label="Account Owner"] .slds-form-element__control,
  records-record-layout-item[field-label="Asset Owner"] .slds-form-element__control, records-record-layout-item[field-label="Quote Owner"] .slds-form-element__control,
  records-record-layout-item[field-label="Order Owner"] .slds-form-element__control, [title="Owner"] + *, .ownerName { filter: blur(7px) !important; }
  .oneUtilityBar, .utilitybar { display: none !important; }
  .slds-split-view_container, .forceSplitViewContainer, .split-left { display: none !important; }`;
(async () => {
  const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1250 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  let first = true, LIGHTNING = null;
  for (const j of jobs) {
    const i = j.indexOf('='), name = j.slice(0, i), p = j.slice(i + 1);
    if (first) { await page.goto(oneTimeUrl(p), { waitUntil: 'domcontentloaded', timeout: 90000 }); first = false; }
    else {
      // Lightning paths load on the lightning domain; a Classic-only object (AccountContactRole) loads embedded (isdtp) on the my.salesforce.com domain
      const base = /^\/lightning\//.test(p) ? LIGHTNING : new URL(LIGHTNING.replace('.lightning.force.com', '.my.salesforce.com')).origin;
      await page.goto(base + p, { waitUntil: 'domcontentloaded', timeout: 90000 });
    }
    if (!LIGHTNING) LIGHTNING = new URL(page.url()).origin;
    await page.waitForTimeout(9000);
    for (let k = 0; k < 3; k++) {   // close one-off promo dialogs (e.g. the Slack announcement); no settings are changed
      const x = page.locator('section[role="dialog"] button[title="Close"], div[role="dialog"] button[title="Close"], .slds-modal button.slds-modal__close').first();
      if (await x.isVisible().catch(() => false)) { await x.click().catch(() => { }); await page.waitForTimeout(1200); } else break;
    }
    await page.addStyleTag({ content: BLUR });
    for (const f of page.frames()) { try { await f.addStyleTag({ content: BLUR }); } catch (e) { } }
    if (/ApexClasses/.test(p)) {   // Setup list: show only the AgenticTelco_ classes (no other org data)
      for (const f of page.frames()) {
        try { await f.evaluate(() => { document.querySelectorAll('table.list tr.dataRow').forEach((r) => { if (!/^AgenticTelco_/.test((r.querySelector('th a, td a[href*="01p"]') || r).textContent.trim()) && !/AgenticTelco_/.test(r.textContent)) r.style.display = 'none'; });
          document.querySelectorAll('table.list').forEach((t) => {   // blur the user-name column (Last Modified By / Created By)
            const hs = [...t.querySelectorAll('tr.headerRow th')].map((h) => h.textContent.trim());
            hs.forEach((h, i) => { if (/Modified By|Created By/.test(h)) t.querySelectorAll('tr.dataRow').forEach((r) => { const c = r.children[i]; if (c) c.style.filter = 'blur(6px)'; }); });
          }); }); } catch (e) { }
      }
    }
    await page.waitForTimeout(800);
    const file = path.join(out, name + '.png');
    const vp = page.viewportSize();   // record pages: crop away the (hidden) list split-view column
    await page.screenshot(/\/lightning\/r\//.test(p) ? { path: file, clip: { x: 270, y: 0, width: vp.width - 270, height: vp.height } }
      : { path: file, clip: { x: 220, y: 0, width: vp.width - 220, height: 820 } });
    console.log('saved ' + file);
  }
  await browser.close();
})().catch((e) => { console.error(String(e.message || e).replace(/https?:\/\/\S+/g, '[url]')); process.exit(1); });
