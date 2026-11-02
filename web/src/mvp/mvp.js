/* AgenticTelco MVP UI, three audience views over one shared replay:
   What changes for the business (tab 1), How it fits (tab 2, the estate), How it's built (tab 3, layer by layer).
   All tab copy comes from one object (web/src/mvp/ui-copy.json, as CFG.ui); layer panel prose comes from docs/mvp/layer-panels.md (CFG.copy).
   Live mode polls the gateway (/api/state); recorded mode replays a recorded run (final /api/state, filtered by time). */
(function () {
  'use strict';
  var CFG = window.MVP_CFG || {}, COPY = CFG.copy, BPMN_XML = CFG.bpmn, REGO = CFG.rego || '', UI = CFG.ui || {};
  var LIVE = CFG.mode === 'live', REC = CFG.recordings || {};
  var UB = UI.business || {}, UC = UI.cio || {}, UD = UI.diagram || {}, UA = UI.architect || {};
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var T = function (x) { return x ? Date.parse(String(x).replace(/([+-]\d\d)(\d\d)$/, '$1:$2')) : NaN; };
  var hm = function (ms) { var d = new Date(ms); return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Europe/London' }); };
  var LAYER_IDS = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8'];
  var CASES = UB.journeys || [{ id: 'happy' }, { id: 'notauth' }, { id: 'overdue' }, { id: 'delayed' }];
  var STEPS = UB.steps || [];
  var OPENING = "We're taking on 15 more staff at the Martlesham office next month, 35 people in total, and moving everyone to cloud video calls. Our broadband already struggles. What do you suggest?";
  var PLATFORM = 'Kubernetes · secrets vault · network zones · API gateway · agent and workload identity · event bus';
  /* step: null = follow the replay, 0..5 = a selected business step, 'all' = whole journey */
  var S = { tab: 'business', caseId: null, cid: null, full: null, t: Infinity, busy: false, open: null, presenter: false, follow: false, play: null, speed: 1, rec: null, step: null };
  var layerCopy = {}; (COPY.layers || []).forEach(function (l) { layerCopy[l.id] = l; });

  function statusKind(s) { s = (s || '').toLowerCase(); if (/^mock/.test(s)) return ['mock', 'Mocked']; if (/mock|stand-in/.test(s)) return ['mix', 'Real + stand-ins']; return ['real', 'Real']; }
  /* no model or runtime names on screen: the agent's model calls read as the agent's own language model */
  function rtName(r) { return /ollama|qwen|llama|gpt|mistral|gemma/i.test(r || '') ? 'Language model (ours)' : (r || ''); }
  /* the delayed journey's Salesforce order number stays off screen */
  function maskNum(s) { var n = S.caseId === 'delayed' && S.full && S.full.links && S.full.links.orderNumber; return n ? String(s).split(n).join('[hidden]') : s; }

  /* ---------- state at time t (recorded replay filters the final state by timestamps) ---------- */
  function view(full, t) {
    if (!full) return null;
    if (t === Infinity) return full;
    var le = function (x) { return T(x) <= t; };
    var v = Object.assign({}, full);
    v.messages = (full.messages || []).filter(function (m) { return le(m.at); });
    v.spans = (full.spans || []).filter(function (s) { return le(s.start_ts); });
    v.decisions = (full.decisions || []).filter(function (d) { return le(d.at); });
    v.consent = (full.consent || []).filter(function (c) { return le(c.at); });
    v.milestones = (full.milestones || []).filter(function (m) { return le(m.at); });
    v.jeopardy = (full.jeopardy || []).filter(function (j) { return le(j.at); });
    v.reports = (full.reports || []).filter(function (r) { return le(r.creationDate); });
    v.bpmn = (full.bpmn || []).filter(function (a) { return le(a.start); }).map(function (a) { return Object.assign({}, a, { end: le(a.end) ? a.end : null }); });
    if (full.intent) {
      var created = T(full.intent.body && full.intent.body.creationDate);
      if (!(created <= t)) v.intent = null;
      else { var st = 'inProgress'; v.reports.forEach(function (r) { var s = r.expression.expressionValue['icm:reportState']; st = /Complies/.test(s) ? 'fulfilled' : /Degrades/.test(s) ? 'atRisk' : st; }); v.intent = Object.assign({}, full.intent, { lifecycle_status: st }); }
    }
    v.spans.forEach(function (s, i) { if (!le(s.end_ts)) v.spans[i] = Object.assign({}, s, { running: true }); });
    return v;
  }
  function nowT() { return S.t === Infinity ? Date.now() : S.t; }
  function hotLayers(v) {
    var now = nowT(), hot = {}, used = {};
    (v ? v.spans : []).forEach(function (s) {
      used[s.layer] = (used[s.layer] || 0) + 1;
      var a = T(s.start_ts), b = s.running ? now : T(s.end_ts);
      if (s.running || now - b < 2500 || (now >= a && now <= b)) hot[s.layer] = s;
    });
    if (v && v.spans.length) { used.L8 = v.spans.length; if (Object.keys(hot).length) hot.L8 = { step: 'Recording ' + v.spans.length + ' steps' }; }
    if (v && v.milestones && v.milestones.some(function (m) { return m.name === 'PortReserved'; })) used.L7 = used.L7 || 1;
    if (v && v.milestones) { var pr = v.milestones.filter(function (m) { return m.name === 'PortReserved' || m.name === 'SentToOSS'; }).pop(); if (pr && now - T(pr.at) < 3000) hot.L7 = { step: pr.name === 'PortReserved' ? 'Access port 150 → 900' : 'Order reaches the network' }; }
    return { hot: hot, used: used };
  }

  /* ---------- the six business steps, as time windows over the recorded run ----------
     Asks → Checks (first agent tool call) → Recommends (first model call after the checks) → Agrees (customer's yes)
     → Ordered (binding policy check in the workflow) → Live (order handed to the network). Spans belong to the step they start in. */
  var winCache = { full: null, n: -1, w: null };
  function byStart(a, b) { return T(a.start_ts) - T(b.start_ts); }
  function windows(full) {
    if (!full) return null;
    var n = (full.spans || []).length + (full.messages || []).length * 1000;
    if (winCache.full === full && winCache.n === n) return winCache.w;
    var sp = (full.spans || []).slice().sort(byStart), msgs = full.messages || [];
    var first = function (pred, after) { for (var i = 0; i < sp.length; i++) { var t = T(sp[i].start_ts); if ((after == null || t > after) && pred(sp[i])) return t; } return null; };
    var users = msgs.filter(function (m) { return m.role === 'user'; });
    var t0 = users.length ? T(users[0].at) : (sp.length ? T(sp[0].start_ts) : null);
    if (sp.length) t0 = Math.min(t0, T(sp[0].start_ts));
    var bChecks = first(function (s) { return s.layer === 'L2' && /^Tool:/.test(s.step); }); if (bChecks == null) bChecks = first(function (s) { return s.layer === 'L4'; });
    var bRec = bChecks == null ? null : first(function (s) { return s.layer === 'L2' && /^Model call$/.test(s.step); }, bChecks);
    var bAgree = null;
    if (bRec != null && users[1]) { bAgree = T(users[1].at); var cm = first(function (s) { return s.layer === 'L1' && /Customer message/.test(s.step); }, bRec); if (cm != null) bAgree = Math.min(bAgree, cm); }
    var bOrder = bAgree == null ? null : first(function (s) { return /Binding policy check/.test(s.step) || s.component === 'Operaton worker'; }, bAgree);
    if (bOrder != null) (full.bpmn || []).forEach(function (a) { if (a.id === 'T_Binding') bOrder = Math.min(bOrder, T(a.start)); });
    var bLive = bOrder == null ? null : first(function (s) { return /OSS|order orchestration/.test(s.step); }, bOrder);
    var starts = [t0, bChecks, bRec, bAgree, bOrder, bLive], w = [];
    for (var i = 0; i < 6; i++) {
      var a = starts[i]; if (a == null || isNaN(a)) { w.push({ a: null, b: null }); continue; }
      var b = Infinity; for (var j = i + 1; j < 6; j++) if (starts[j] != null) { b = starts[j]; break; }
      w.push({ a: i === 0 ? -Infinity : a, b: b, a0: a });
    }
    var adv = (full.decisions || []).filter(function (d) { return d.mode === 'advisory'; });
    w.blocked = adv.length > 0 && !adv.some(function (d) { return d.result.allow; });
    w.denyReason = w.blocked ? (adv[0].result.deny || [])[0] : null;
    winCache = { full: full, n: n, w: w };
    return w;
  }
  function stepAt(W, t) { var k = -1; if (!W) return k; for (var i = 0; i < 6; i++) if (W[i].a != null && W[i].a0 <= t) k = i; return k; }
  function selStep() {   // the step tabs 2 and 3 show: the selected one, else the replay's current one
    if (S.step === 'all') return 'all';
    if (S.step != null) return S.step;
    var W = windows(S.full); if (!W) return null;
    if (!LIVE && S.rec && !S.play && S.t >= S.rec.tEnd) return 'all';   // replay finished: show the whole journey
    var k = stepAt(W, nowT()); return k < 0 ? null : k;
  }
  function isLive(v) { return !!(v && (v.milestones || []).some(function (m) { return m.name === 'Live'; })); }
  function stepKinds(v) {
    var W = windows(S.full), t = nowT(), out = [];
    var cur = stepAt(W, t), asst = v ? v.messages.filter(function (m) { return m.role === 'assistant'; }) : [];
    var blockedNow = W && W.blocked && asst.length > 0, live = isLive(v), jeo = v && (v.jeopardy || []).length && !live;
    for (var i = 0; i < 6; i++) {
      var c = STEPS[i] || {}, k = '', sub = c.sub || '';
      if (S.caseId === 'notauth' && c.subNotauth) sub = c.subNotauth;
      if (!W || !v) { out.push({ k: '', b: c.label, s: sub }); continue; }
      if (W[i].a == null) { if (W.blocked) { k = blockedNow ? 'skip' : ''; sub = c.subSkip || sub; } }
      else if (W[i].a0 <= t) k = i < cur ? 'done' : 'now';
      if (i === 2 && W.blocked) { sub = W.denyReason === 'overdue_balance' ? (c.subOverdue || sub) : (c.subNotauth || sub); if (blockedNow) k = 'blocked'; }
      if (i === 4 && k && S.caseId !== 'delayed' && S.full.links && S.full.links.orderNumber && (v.milestones || []).some(function (m) { return m.name === 'OrderInProgress'; })) sub = 'Order ' + S.full.links.orderNumber;
      if (i === 5 && jeo) { k = 'delay'; sub = c.subDelay || sub; }
      if (i === 5 && live) { k = 'live'; var d = liveDate(v); sub = (S.caseId === 'delayed' ? 'Live ' : 'Fibre 900 live ') + (d ? d.replace(/ \d{4}$/, '') : '') + (S.caseId === 'delayed' ? ' · ' + delayDays(v) + ' days late, Sam told first' : ''); }
      out.push({ k: k, b: c.label, s: sub });
    }
    return out;
  }
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  function shortDate(iso) { var d = new Date(iso + 'T12:00:00Z'); return d.getUTCDate() + ' ' + MONTHS[d.getUTCMonth()].slice(0, 3) + ' ' + d.getUTCFullYear(); }
  function liveDate(v) {   // the live date the agent told the customer, from its proactive message
    var m = (v.messages || []).filter(function (x) { return x.meta && x.meta.proactive && /Complies/.test(x.meta.reportState || ''); }).pop();
    var r = m && m.content.match(new RegExp('(\\d{1,2}) (' + MONTHS.join('|') + ') (\\d{4})'));
    return r ? r[1] + ' ' + r[2].slice(0, 3) + ' ' + r[3] : null;
  }
  function dur(ms) { var s = Math.round(ms / 1000), m = Math.floor(s / 60); return (m ? m + ' min ' : '') + (s % 60) + ' s'; }

  /* ---------- derived business facts ---------- */
  function facts(v) {
    var st = (v && v.state) || {}, pack = st.contextPack || {}, f = {};
    f.name = st.contactFullName || '';
    f.who = st.contactFullName ? st.contactFullName + ', ' + ((UB.people || {})[st.contactFullName] || st.contactRole) : '—';
    f.current = (pack.currentBroadband && ((pack.currentBroadband.product || pack.currentBroadband.name) + ' · £' + pack.currentBroadband.monthlyPriceGBP + ' a month')) || 'AgenticTelco Fibre 150 · £27 a month';
    var ce = (pack.contractMonthsLeft || {}).contractEnd; f.contractEnd = ce ? new Date(ce + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '28 August 2027';
    f.contractShort = ce ? shortDate(ce) : '28 Aug 2027';
    f.site = UB.site || 'Site 4471, Martlesham';
    return f;
  }

  /* ---------- page shell ---------- */
  function shell() {
    var H = UI.header || {};
    document.title = 'AgenticTelco MVP · Agent upgrades a Business Customer Service (B2B)';
    $('#app').innerHTML =
      '<header class="hd"><div class="brand">' + (CFG.mark || '') + '<div><div class="brand-name">AgenticTelco</div><div class="brand-sub">TelForce business portal</div></div></div>' +
      '<div class="ttl"><div class="kick">' + esc(H.kicker) + '</div><h1>' + esc(H.title) + '</h1></div>' +
      '<button class="tb" id="b-pres" title="Presenter mode (P)">Presenter</button>' + (LIVE ? '' : '<button class="tb" id="btn-lock" title="Lock">Lock</button>') + '</header>' +
      '<nav class="tabs" role="tablist">' + (UI.tabs || []).map(function (t) { return '<button role="tab" data-tab="' + t.id + '"><b>' + tabIcon(t.id) + esc(t.label) + '</b><span>' + esc(t.subtitle) + '</span></button>'; }).join('') + '</nav>' +
      '<div class="modebar' + (LIVE ? '' : ' rec') + '" id="modebar"></div>' +
      '<main><section id="v-business"></section><section id="v-cio" hidden></section><section id="v-architect" hidden></section></main>' +
      '<div class="dr" id="drawer" aria-hidden="true"></div>' +
      '<div class="foot">Concept demo by Lalit Chauhan · not an official Salesforce product</div>';
    shellBusiness(); shellCio(); shellArchitect();
    $$('.tabs button').forEach(function (b) { b.onclick = function () { setTab(b.dataset.tab); }; });
    $('#b-pres').onclick = togglePresenter;
    document.addEventListener('click', function (e) {
      var st = e.target.closest && e.target.closest('[data-step]'); if (st) { selectStep(st.dataset.step); return; }
      var go = e.target.closest && e.target.closest('[data-goto]'); if (go) { e.preventDefault(); setTab(go.dataset.goto); return; }
      var ab = e.target.closest && e.target.closest('[data-about]'); if (ab) { openLayer(ab.dataset.about); }
    });
    document.addEventListener('keydown', function (e) {
      if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.key === 'Escape') closeLayer(); else if (e.key === 'p' || e.key === 'P') togglePresenter();
      else if (/^[1-4]$/.test(e.key)) startCase(CASES[+e.key - 1].id); else if (e.key === ' ' && !LIVE) { e.preventDefault(); togglePlay(); }
    });
    setTab('business'); modebar(); render();
  }
  function setTab(t) {
    S.tab = t;
    $$('.tabs button').forEach(function (b) { var on = b.dataset.tab === t; b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); });
    ['business', 'cio', 'architect'].forEach(function (x) { $('#v-' + x).hidden = x !== t; });
    archKey = ''; render(); window.scrollTo(0, 0);
  }
  function selectStep(x) {
    if (x === 'follow') S.step = null; else if (x === 'all') S.step = S.step === 'all' ? null : 'all';
    else { x = +x; S.step = S.step === x ? null : x; }
    archKey = ''; render();
  }
  var TAB_ICON = {   // thin 24x24 line icons beside each tab heading, inline (offline), one accent colour
    business: '<path d="M12 20V4M6 10l6-6 6 6"/>',   // upward arrow
    cio: '<circle cx="5.5" cy="6" r="2.5"/><circle cx="18.5" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M8 6h8M7 8.2l3.6 7.6M17 8.2l-3.6 7.6"/>',   // connected nodes
    architect: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/>'   // code brackets
  };
  function tabIcon(id) { return TAB_ICON[id] ? '<svg class="tic" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' + TAB_ICON[id] + '</svg>' : ''; }
  function togglePresenter() { S.presenter = !S.presenter; document.body.classList.toggle('presenter', S.presenter); $('#b-pres').classList.toggle('on', S.presenter); }

  function modebar() {
    var m = $('#modebar');
    if (LIVE) { m.innerHTML = '<span class="badge">LIVE</span><span>Live run against the real Salesforce org, our agent, workflow and policy. Legacy systems are labelled stand-ins.</span><span class="sp"></span><span id="mstat"></span>'; return; }
    var r = S.rec;
    m.innerHTML = '<span class="badge">RECORDED RUN</span><span class="mtxt">' + (r ? 'Recorded run of “' + esc(r.title) + '” on ' + esc(new Date(r.recordedAt).toLocaleString('en-GB', { timeZone: 'Europe/London', dateStyle: 'medium', timeStyle: 'short' })) + ' (UK time), replayed from the real data it produced. Long waits are shortened.' : 'Recorded runs: choose a journey to replay what really happened.') + '</span><span class="sp"></span>' +
      '<span class="ctrl"><button class="tb" id="b-play">' + (S.play ? 'Pause' : 'Play') + '</button><input type="range" id="scrub" min="0" max="1000" value="0" aria-label="Replay position"><button class="tb" id="b-end">Skip to end</button>' +
      '<select id="spd" class="tb" aria-label="Speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></span>';
    $('#b-play').onclick = togglePlay; $('#b-end').onclick = function () { if (S.rec) { stopPlay(); S.t = S.rec.tEnd; render(); } };
    $('#spd').value = String(S.speed); $('#spd').onchange = function () { S.speed = +this.value; };
    $('#scrub').oninput = function () { if (!S.rec) return; stopPlay(); S.t = S.rec.timeAt(+this.value / 1000); render(); };
  }

  function render() {
    var v = view(S.full, S.t);
    renderBusiness(v);
    if (S.tab === 'cio') renderCio(v);
    if (S.tab === 'architect') renderArchitect(v);
    if (S.open) renderLayer(S.open, v);
    if (!LIVE && S.rec && $('#scrub')) { $('#scrub').value = Math.round(S.rec.fracAt(S.t) * 1000); }
    if (LIVE && $('#mstat')) $('#mstat').textContent = S.busy ? 'agent working…' : (S.cid ? 'conversation ' + S.cid : '');
  }

  /* ---------- 1. What changes for the business ---------- */
  function shellBusiness() {
    $('#v-business').innerHTML = '<div class="bv">' +
      '<div class="jrow"><div class="jl">' + esc(UB.journeysHeading) + '</div><div class="cases">' + CASES.map(function (c, i) { return '<button class="case" data-case="' + c.id + '"><b>' + (i + 1) + '. ' + esc(c.title) + '</b><span>' + esc(c.sub) + '</span></button>'; }).join('') + '</div></div>' +
      '<div class="chev" id="chev"></div><div class="stephint" id="stephint"></div>' +
      '<div class="bgrid"><div class="panel chatp"><div class="portal"><div class="av" id="av">S</div><div class="who" id="who"></div><span class="badge" id="ist"></span></div>' +
      '<div class="chat" id="chat"></div>' +
      (LIVE ? '<div class="quick" id="quick"></div><div class="composer"><textarea id="msg" placeholder="Type as the customer…"></textarea><button class="btn" id="send">Send</button></div>' : '') + '</div>' +
      '<div class="bside"><div class="card today" id="today"></div><div class="card outcome" id="outcome"></div><div class="card kpis" id="kpis" hidden></div></div></div></div>';
    $$('.case').forEach(function (b) { b.onclick = function () { startCase(b.dataset.case); }; });
    if (LIVE) { $('#send').onclick = function () { send($('#msg').value); }; $('#msg').onkeydown = function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send($('#msg').value); } }; }
  }
  function renderBusiness(v) {
    var cid = S.caseId, kinds = stepKinds(v), sel = S.step;
    $$('.case').forEach(function (b) { b.classList.toggle('on', b.dataset.case === cid); b.disabled = S.busy && LIVE; });
    var ch = kinds.map(function (c, i) { return '<button class="cv ' + c.k + (sel === i ? ' sel' : '') + '" data-step="' + i + '" title="Show this step in How it fits and How it\'s built"><b>' + esc(c.b) + '</b><span>' + esc(c.s) + '</span></button>'; }).join('');
    if ($('#chev').dataset.k !== ch) { $('#chev').innerHTML = ch; $('#chev').dataset.k = ch; }
    var hint = sel === null || sel === 'all' ? esc(UB.stepHint) + ' <a href="#" data-goto="cio">' + esc(UB.stepHintLink) + ' →</a>'
      : 'Selected: <b>' + esc((STEPS[sel] || {}).label) + '</b> · <a href="#" data-goto="cio">' + esc(UB.stepHintLink) + ' →</a> · <a href="#" data-step="follow">Follow the replay</a>';
    if ($('#stephint').innerHTML !== hint) $('#stephint').innerHTML = hint;
    var st = (v && v.state) || {}, f = facts(v);
    $('#av').textContent = (st.contactName || 'S')[0];
    $('#who').innerHTML = st.contactFullName ? '<b>' + esc(f.who) + '</b><span>Business portal chat · ' + esc(UB.customer) + '</span>' : '<b>Business portal chat</b><span>' + esc(UB.customer) + '</span>';
    var k5 = kinds[5] ? kinds[5].k : '', k2 = kinds[2] ? kinds[2].k : '', k4 = kinds[4] ? kinds[4].k : '';
    var badge = k5 === 'live' ? ['Live', 'ok'] : k5 === 'delay' ? ['Delayed, customer told', 'warn'] : k2 === 'blocked' ? ['No order', 'no'] : k4 ? ['Order placed', ''] : ['', ''];
    $('#ist').textContent = badge[0]; $('#ist').className = 'badge ' + badge[1]; $('#ist').hidden = !badge[0];
    renderChat(v);
    var live = isLive(v);
    $('#today').innerHTML = '<h3>' + esc(UB.todayHeading) + '</h3><dl><dt>Customer</dt><dd>' + esc(UB.customer) + ' · ' + esc(f.site) + '</dd><dt>Asking</dt><dd>' + esc(f.who) + '</dd><dt>Service</dt><dd>' + esc(f.current) + '</dd><dt>Contract end</dt><dd>' + esc(f.contractEnd) + '</dd></dl>';
    var o = outcome(v, f);
    $('#outcome').innerHTML = '<h3>' + esc(k2 === 'blocked' ? UB.outcomeHeadingNo : UB.outcomeHeading) + '</h3>' + o;
    $('#outcome').classList.toggle('done', live); $('#outcome').classList.toggle('no', k2 === 'blocked');
    var kp = kpis(v); $('#kpis').hidden = !kp; if (kp) $('#kpis').innerHTML = '<h3>' + esc(UB.kpiHeading) + '</h3>' + kp;
  }
  function outcome(v, f) {
    if (!v) return '<p class="muted">' + esc(UB.outcomeWaiting) + '</p>';
    var W = windows(S.full), asst = v.messages.filter(function (m) { return m.role === 'assistant'; });
    if (W && W.blocked && asst.length) {
      var od = (((v.state || {}).contextPack || {}).overdueBalance || {}).amountGBP;
      return '<div class="big no">' + esc(UB.outcomeNoOrder) + '</div>' + (W.denyReason === 'overdue_balance'
        ? '<p>The overdue balance of <b>£' + Number(od || 0).toFixed(2) + '</b> must be paid first. The agent sent ' + esc(f.name.split(' ')[0] || 'the customer') + ' a payment link (mocked).</p>'
        : '<p>' + esc(f.name.split(' ')[0] || 'The requester') + ' is not authorised to order. The agent asked them to bring in Sam Taylor, the authorised contact.</p>') + '<p class="muted">Nothing was quoted, ordered or changed.</p>';
    }
    if (!isLive(v)) {
      var jeo = (v.jeopardy || []).slice(-1)[0];
      if (jeo) return '<div class="big warn">Delayed by ' + delayDays(v) + ' days</div><p>No exchange port is free yet. ' + esc(f.name.split(' ')[0] || 'The customer') + ' was told the new date (' + esc(shortDate(jeo.body['x-revisedCompletionDate'])) + ') before it slipped.</p>';
      return '<p class="muted">' + esc(UB.outcomeWaiting) + '</p>';
    }
    var pack = (v.state || {}).contextPack || {}, prod = (v.milestones.filter(function (m) { return m.name === 'Live'; })[0].body || {}).product || 'AgenticTelco Fibre 900';
    var off = (pack.offerings || []).filter(function (o) { return o.name === prod; })[0] || {};
    var rows = [['Service', esc(prod.replace(/^AgenticTelco /, ''))], ['Price', '£' + esc(off.monthlyPriceGBP || 45) + ' a month'], ['Contract end', esc(f.contractShort) + ' <span class="muted">(unchanged)</span>']];
    if (S.caseId !== 'delayed' && v.links && v.links.orderNumber) rows.push(['Order', '<span class="mono">' + esc(v.links.orderNumber) + '</span>']);
    var ld = liveDate(v); rows.push(['Live', esc(ld || '') + (S.caseId === 'delayed' ? ' <span class="muted">(' + delayDays(v) + ' days later than planned; customer told first)</span>' : '')]);
    return '<div class="big ok">' + esc(prod.replace(/^AgenticTelco /, '')) + ' is live</div>' + (planOf(v) ? '<p class="orl">' + esc(UB.orchestrationLine) + '</p>' : '') + '<dl>' + rows.map(function (r) { return '<dt>' + r[0] + '</dt><dd>' + r[1] + '</dd>'; }).join('') + '</dl>';
  }
  function delayDays(v) {
    var j = (S.full.jeopardy || [])[0], s = (S.full.milestones || []).filter(function (m) { return m.name === 'SentToOSS'; })[0];
    if (!j || !s) return 2;
    return Math.round((T(j.body['x-revisedCompletionDate'] + 'T12:00:00Z') - T(s.body.expectedCompletionDate + 'T12:00:00Z')) / 864e5);
  }
  function kpis(v) {
    if (!v) return '';
    var W = windows(S.full), asst = v.messages.filter(function (m) { return m.role === 'assistant'; }), live = isLive(v);
    if (!(live || (W && W.blocked && asst.length))) return '';
    var users = v.messages.filter(function (m) { return m.role === 'user'; }), pro = asst.filter(function (m) { return m.meta && m.meta.proactive; });
    var orders = v.milestones.filter(function (m) { return m.name === 'OrderInProgress'; }).length, k = [];
    if (live && S.caseId !== 'delayed') { var lv = v.milestones.filter(function (m) { return m.name === 'Live'; })[0]; k.push([dur(T(lv.at) - T(users[0].at)), 'request to live (demo run)']); }
    k.push([v.spans.length, 'automated steps, all logged']);
    k.push([users.length, users.length === 1 ? 'customer message' : 'customer messages']);
    if (live) k.push([pro.length, pro.length === 1 ? 'proactive update' : 'proactive updates']); else k.push([orders, 'orders placed']);
    return '<div class="kg">' + k.map(function (x) { return '<div><b>' + esc(x[0]) + '</b><span>' + esc(x[1]) + '</span></div>'; }).join('') + '</div>' + (live ? '<p class="muted small">' + esc(UB.kpiNote) + '</p>' : '');
  }
  function linkify(t) { return esc(t).replace(/(https:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>'); }
  function renderChat(v) {
    var c = $('#chat'), msgs = v ? v.messages : [];
    var html = msgs.map(function (m) {
      var pro = m.meta && m.meta.proactive, ok = pro && /Complies/.test(m.meta.reportState || '');
      return '<div class="msg ' + m.role + (pro ? ' pro' + (ok ? ' ok' : '') : '') + '">' + linkify(m.content) + '<span class="meta">' + (m.role === 'user' ? esc((v.state || {}).contactName || 'Customer') : 'AgenticTelco agent' + (pro ? ' · proactive update' : '')) + ' · ' + hm(T(m.at)) + '</span></div>';
    }).join('');
    var lastUser = msgs.length && msgs[msgs.length - 1].role === 'user';
    if ((LIVE && S.busy) || (!LIVE && lastUser)) html += '<div class="typing">Agent is checking…</div>';
    if (!msgs.length) html = '<div class="empty">' + (S.caseId ? (LIVE ? 'Press Send to ask the opening question as the customer.' : esc(UB.chatReady)) : esc(UB.chatEmpty)) + '</div>';
    var key = msgs.length + '|' + (S.busy ? 1 : 0) + '|' + lastUser + S.caseId;
    if (c.dataset.k !== key) { c.innerHTML = html; c.dataset.k = key; c.scrollTop = c.scrollHeight; }
    if (LIVE) {
      var q = [];
      if (S.cid && !msgs.length) q.push(OPENING);
      if (S.cid && msgs.length && !(v.consent || []).length && (v.decisions || []).some(function (d) { return d.result.allow; }) && S.caseId !== 'notauth' && S.caseId !== 'overdue') q.push('Yes please, go ahead.');
      $('#quick').innerHTML = q.map(function (x) { return '<button>' + esc(x.length > 60 ? x.slice(0, 58) + '…' : x) + '</button>'; }).join('');
      $('#quick').querySelectorAll('button').forEach(function (b, i) { b.onclick = function () { send(q[i]); }; });
    }
  }

  /* ---------- 2. How it fits: the estate as a layered picture, lit by step ---------- */
  var ICON = {   // simple 24x24 line icons, drawn in code
    person: '<circle cx="12" cy="7" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    chat: '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    agent: '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4M9.5 13h.01M14.5 13h.01M9 16.5h6"/><circle cx="12" cy="3.5" r="1"/>',
    shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    db: '<ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>',
    flow: '<rect x="2.5" y="9" width="5" height="6" rx="1"/><rect x="9.5" y="9" width="5" height="6" rx="1"/><rect x="16.5" y="9" width="5" height="6" rx="1"/><path d="M7.5 12h2M14.5 12h2"/>',
    api: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 5l-3 14"/>',
    cloud: '<path d="M7 18h10.5a4 4 0 0 0 .5-8 6 6 0 0 0-11.5-1.5A4.8 4.8 0 0 0 7 18z"/>',
    server: '<rect x="4" y="4" width="16" height="6" rx="1.5"/><rect x="4" y="14" width="16" height="6" rx="1.5"/><path d="M8 7h.01M8 17h.01"/>',
    bill: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
    pin: '<path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/>',
    net: '<circle cx="5" cy="12" r="2.5"/><circle cx="19" cy="5" r="2.5"/><circle cx="19" cy="19" r="2.5"/><path d="M7.3 11l9.4-5M7.3 13l9.4 5"/>',
    timeline: '<path d="M4 6h9M7 12h11M5 18h7"/><path d="M3 3v18"/>'
  };
  /* node: [id, x, y, w, h, icon, colour var, mocked] ; diagram text comes from UI.diagram */
  var DNODES = [
    ['customer', 16, 56, 104, 132, 'person', '--navy'],
    ['L1', 148, 56, 156, 132, 'chat', '--l1'], ['L2', 328, 56, 156, 132, 'agent', '--l2'],
    ['L4', 524, 56, 156, 132, 'shield', '--l4'], ['L3', 704, 56, 156, 132, 'db', '--l3'],
    ['L5', 900, 56, 144, 132, 'flow', '--l5'],
    ['api', 148, 256, 896, 56, 'api', '--l6'],
    ['sf', 148, 340, 352, 152, 'cloud', '--blue'],
    ['sfcust', 156, 396, 336, 22, '', '--blue'], ['sfcat', 156, 424, 108, 62, '', '--blue'], ['sfcpq', 270, 424, 108, 62, '', '--blue'], ['sfom', 384, 424, 108, 62, '', '--blue'],
    ['billing', 528, 366, 160, 118, 'bill', '--legacy', 1], ['avail', 700, 366, 160, 118, 'pin', '--legacy', 1], ['oss', 872, 366, 160, 118, 'server', '--legacy', 1],
    ['L8', 1084, 56, 168, 200, 'timeline', '--l8'], ['L7', 1084, 296, 168, 196, 'net', '--l7', 1]];
  var DGROUPS = { understand: [136, 16, 360, 188, '--l2'], know: [512, 16, 360, 188, '--l4'], act: [888, 16, 168, 188, '--l5'], connect: [136, 220, 920, 284, '--l6'], prove: [1072, 16, 192, 488, '--l8'] };
  var DEDGES = [['customer', 'L1', 'M120 122H148'], ['L1', 'L2', 'M304 122H328'], ['L2', 'L4', 'M484 122H524'], ['L4', 'L3', 'M680 122H704'],
    ['L1', 'L5', 'M226 188V212H972V188'], ['L4', 'api', 'M602 188V256'], ['L5', 'api', 'M972 212V256'], ['L3', 'L8', 'M782 56V8H1168V56'],
    ['api', 'sf', 'M324 312V340'], ['api', 'billing', 'M608 312V366'], ['api', 'avail', 'M780 312V366'], ['api', 'oss', 'M952 312V366'], ['oss', 'L7', 'M1032 425H1084'], ['sfom', 'oss', 'M438 486V514H952V484']];
  function wrapText(s, max) { var w = String(s || '').split(' '), out = [], cur = ''; w.forEach(function (x) { if ((cur + ' ' + x).trim().length > max && cur) { out.push(cur); cur = x; } else cur = (cur + ' ' + x).trim(); }); if (cur) out.push(cur); return out; }
  function icon(name, x, y, s, col) { return '<g class="ic" transform="translate(' + x + ' ' + y + ') scale(' + (s / 24) + ')" fill="none" stroke="' + col + '" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + ICON[name] + '</g>'; }
  function diagramSvg() {
    var N = UD.nodes || {}, G = {}, chips = UD.chips || {}; (UD.groups || []).forEach(function (g) { G[g.id] = g; });
    var h = '<svg class="dsvg" id="dsvg" viewBox="0 0 1280 526" role="img" aria-label="' + esc(UC.headline) + '"><defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="context-stroke"/></marker><marker id="aht" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#7d8494"/></marker></defs>';
    Object.keys(DGROUPS).forEach(function (k) { var g = DGROUPS[k]; h += '<g class="dg" data-group="' + k + '"><rect x="' + g[0] + '" y="' + g[1] + '" width="' + g[2] + '" height="' + g[3] + '" rx="14" style="--c:var(' + g[4] + ')"/><text x="' + (g[0] + 14) + '" y="' + (g[1] + 24) + '" class="gt">' + esc(((G[k] || {}).title || k).toUpperCase()) + '</text></g>'; });
    h += '<g class="older"><rect x="516" y="330" width="528" height="166" rx="10"/><text x="528" y="352" class="ot">' + esc(chips.adapters || 'Adapters') + ' · older systems</text></g>';
    DEDGES.forEach(function (e) { h += '<path class="de" data-e="' + e[0] + '-' + e[1] + '" d="' + e[2] + '" marker-end="url(#ah)"/>'; });
    DNODES.forEach(function (n) {
      var id = n[0], x = n[1], y = n[2], w = n[3], ht = n[4], t = id === 'customer' ? (UD.customer || {}) : (N[id] || {}), col = 'var(' + n[6] + ')';
      var lay = /^L\d$/.test(id) ? id : id === 'api' || /^sf/.test(id) || id === 'billing' || id === 'avail' || id === 'oss' ? 'L6' : '';
      h += '<g class="dn" data-node="' + id + '"' + (lay ? ' data-about="' + lay + '"' : '') + ' style="--c:' + col + '" tabindex="0"><title>' + esc(t.title) + (lay ? ' (' + lay + ')' : '') + '</title><rect class="bx" x="' + x + '" y="' + y + '" width="' + w + '" height="' + ht + '" rx="12"/>';
      if (id === 'api') {
        h += '<circle cx="' + (x + 28) + '" cy="' + (y + 28) + '" r="18" class="icb"/>' + icon('api', x + 17, y + 17, 22, col) +
          '<text x="' + (x + 56) + '" y="' + (y + 25) + '" class="nt">' + esc(t.title) + '</text><text x="' + (x + 56) + '" y="' + (y + 43) + '" class="ns">' + esc(t.sub) + ' · L6</text>' +
          '<g class="chipg"><rect x="' + (x + 686) + '" y="' + (y + 15) + '" width="196" height="26" rx="13" class="chs"/><text x="' + (x + 784) + '" y="' + (y + 32) + '" text-anchor="middle">' + esc(chips.sf) + '</text></g>';
      } else if (id === 'sf') {
        var B = UD.sfBand || {};
        h += '<g class="sfband"><rect class="fa" x="' + (x + 6) + '" y="' + (y + 6) + '" width="' + (w - 12) + '" height="26" rx="6"/><text x="' + (x + w / 2) + '" y="' + (y + 23) + '" text-anchor="middle">' + esc(B.label) + '</text></g>' +
          icon('cloud', x + 10, y + 36, 18, col) + '<text x="' + (x + 34) + '" y="' + (y + 50) + '" class="nt">' + esc(t.title) + '</text><text x="' + (x + w - 10) + '" y="' + (y + 50) + '" text-anchor="end" class="ns">' + esc(t.sub) + '</text>';
      } else if (id === 'sfcust') {
        h += '<text x="' + (x + 10) + '" y="' + (y + 15) + '" class="ns sb">' + esc(t.title) + ' (' + esc(t.sub) + ')</text>';
      } else if (/^sf/.test(id)) {
        h += '<text x="' + (x + 8) + '" y="' + (y + 16) + '" class="nt sb">' + esc(t.title) + ':</text>';
        wrapText(t.sub, 16).slice(0, 3).forEach(function (ln, i) { h += '<text x="' + (x + 8) + '" y="' + (y + 31 + i * 12) + '" class="ns">' + esc(ln) + '</text>'; });
      } else {
        var cx = id === 'customer' ? x + w / 2 : x + 30;
        h += '<circle cx="' + cx + '" cy="' + (y + 30) + '" r="19" class="icb"/>' + icon(n[5], cx - 12, y + 18, 24, col);
        var tx = id === 'customer' ? x + w / 2 : x + 14, anc = id === 'customer' ? ' text-anchor="middle"' : '';
        h += '<text x="' + tx + '" y="' + (y + 72) + '" class="nt"' + anc + '>' + esc(t.title) + '</text>';
        wrapText(t.sub, Math.floor((w - 24) / 6.4)).slice(0, 3).forEach(function (ln, i) { h += '<text x="' + tx + '" y="' + (y + 92 + i * 16) + '" class="ns"' + anc + '>' + esc(ln) + '</text>'; });
        if (lay && !/^sf/.test(id) && id !== 'billing' && id !== 'avail' && id !== 'oss') h += '<text x="' + (x + w - 12) + '" y="' + (y + 22) + '" text-anchor="end" class="ln">' + lay + '</text>';
        if (UD.adapters && UD.adapters[id]) h += '<text x="' + (x + w - 10) + '" y="' + (y + 22) + '" text-anchor="end" class="ad">' + esc(UD.adapters[id]) + '</text>';
        if (n[7]) h += '<g class="mk"><rect x="' + (x + w - 64) + '" y="' + (y + ht - 28) + '" width="54" height="18" rx="9"/><text x="' + (x + w - 37) + '" y="' + (y + ht - 15) + '" text-anchor="middle">' + esc(chips.mocked || 'Mocked') + '</text></g>';
      }
      h += '</g>';
    });
    var OR = UD.orchestration || {};   // Salesforce order orchestration sends the network order through the network order adapter (mocked)
    h += '<g class="olbl"><rect x="540" y="506" width="290" height="17" rx="8"/><text x="685" y="518" text-anchor="middle">' + esc(OR.label) + '</text></g>' +
      '<g class="mk"><rect x="838" y="506" width="54" height="17" rx="8"/><text x="865" y="518" text-anchor="middle">' + esc(OR.tag || chips.mocked || 'Mocked') + '</text></g>';
    return h + '</svg>';
  }
  function shellCio() {
    var ev = CFG.evidence || [];
    $('#v-cio').innerHTML = '<div class="cio">' +
      '<h2 class="hl">' + esc(UC.headline) + '</h2>' +
      '<div class="banner"><div class="big">' + esc(UC.banner).replace(/ · /g, '<i>·</i>') + '</div><div class="small">' + esc(UC.bannerSmall) + '</div></div>' +
      '<div class="c3">' + (UC.cards || []).map(function (c, i) { return '<div class="cc"><div class="ci">' + '<svg viewBox="0 0 24 24" width="26" height="26">' + icon(['agent', 'shield', 'flow'][i], 0, 0, 24, 'currentColor') + '</svg></div><div><b>' + esc(c.title) + '</b><p>' + esc(c.text) + '</p></div></div>'; }).join('') + '</div>' +
      '<div class="cmain"><div class="panel dgm"><div class="strip" id="cstrip"></div><div class="dcap" id="dcap"></div>' + diagramSvg() +
      '<div class="glegend">' + (UD.groups || []).map(function (g) { return '<div><b>' + esc(g.title) + '</b> ' + esc(g.text) + '</div>'; }).join('') + '<div class="tl"><b>' + esc((UD.orchestration || {}).legendTitle) + '</b> ' + esc((UD.orchestration || {}).legend) + '</div></div>' +
      '<div class="dtree" id="dtree"></div></div>' +
      '<div class="msgs">' + (UC.messages || []).map(function (m) { return '<div class="mc"><b>' + esc(m.title) + '</b><p>' + esc(m.text) + '</p></div>'; }).join('') + '</div></div>' +
      '<div class="gal" id="gallery"><h2>' + esc(UC.galleryHeading) + '</h2><p class="small">' + esc(UC.galleryIntro) + '</p>' +
      (ev.length ? '<div class="evg">' + ev.map(function (e, i) { return '<figure class="ev"><img loading="lazy" alt="' + esc(e.caption) + '" src="' + e.src + '"><figcaption><b>' + (i + 1) + '.</b> ' + esc(e.caption) + '</figcaption></figure>'; }).join('') + '</div>' : '<p class="small">No screenshots in this build.</p>') + '</div></div>';
    $$('.ev img').forEach(function (im) { im.onclick = function () { var w = window.open(); if (w) w.document.write('<img style="max-width:100%" src="' + im.src + '">'); }; });
  }
  /* which diagram nodes a set of spans and events touches */
  function litNodes(spans, msgs, mss) {
    var on = {};
    spans.forEach(function (s) {
      on[s.layer] = 1; on.L8 = 1;
      if (s.layer === 'L1' && /Customer message/.test(s.step)) on.customer = 1;
      if (s.layer === 'L6') {
        on.api = 1; var r = (s.runtime || '') + ' ' + s.step + ' ' + (s.component || '');
        if (isSfRt(s.runtime) || /Salesforce/.test(s.runtime || '')) {
          on.sf = 1; var a = s.api || '';
          if (/TMF620/.test(a)) on.sfcat = 1;
          if (/TMF648|TMF671/.test(a)) on.sfcpq = 1;
          if (/TMF622|TMF637/.test(a)) on.sfom = 1;
          if (/TMF629|TMF632/.test(a)) on.sfcust = 1;
        }
        if (/Billing|Payment/i.test(r)) on.billing = 1; if (/Availability/i.test(r)) on.avail = 1; if (/OSS/.test(r)) on.oss = 1;
        if (/network order adapter/i.test(r)) { on.sfom = 1; on.oss = 1; }
      }
    });
    if (msgs.length) on.customer = 1;
    if (mss.some(function (m) { return /SentToOSS|PortReserved|Jeopardy|Live/.test(m.name); })) on.L7 = 1;
    if (mss.some(function (m) { return (m.name === 'SentToOSS' && (m.body || {}).via) || m.name === 'FulfilmentPlan'; })) { on.sfom = 1; on.oss = 1; on.sf = 1; on.api = 1; }
    return on;
  }
  function inWin(W, k) { var w = k === 'all' ? { a: -Infinity, b: Infinity } : W[k]; return function (x) { var t = T(x); return w.a != null && t >= w.a && t < w.b; }; }
  function renderCio(v) {
    var W = windows(S.full), k = selStep(), kinds = stepKinds(v);
    var strip = '<span class="sl">' + esc(UC.stepsLabel) + '</span>' + kinds.map(function (c, i) { return '<button class="pill ' + c.k + (S.step === i ? ' sel' : '') + (k === i && S.step === null ? ' cur' : '') + '" data-step="' + i + '">' + esc(c.b) + '</button>'; }).join('') +
      '<button class="pill all' + (S.step === 'all' ? ' sel' : '') + '" data-step="all">' + esc(UC.allSteps) + '</button>';
    if ($('#cstrip').dataset.k !== strip) { $('#cstrip').innerHTML = strip; $('#cstrip').dataset.k = strip; }
    var svg = $('#dsvg'), on = {}, src = null, cap;
    if (!v || k == null || !W) { svg.classList.remove('active'); cap = S.caseId ? 'Press Play: the layers light up as the replay reaches each step.' : 'Choose a journey in What changes for the business, then press Play or pick a step: the layers it uses light up here.'; }
    else {
      var f = inWin(W, k), selected = S.step !== null;
      src = selected ? S.full : v;   // a selected step shows everything it uses; following the replay shows what has happened so far
      on = W[k === 'all' ? 0 : k] && (k === 'all' || W[k].a != null) ? litNodes((src.spans || []).filter(function (s) { return f(s.start_ts); }), (src.messages || []).filter(function (m) { return f(m.at); }), (src.milestones || []).filter(function (m) { return f(m.at); })) : {};
      svg.classList.add('active');
      var names = DNODES.filter(function (n) { return on[n[0]]; }).map(function (n) { var t = n[0] === 'customer' ? UD.customer : (UD.nodes || {})[n[0]]; return (t || {}).title; });
      var lbl = k === 'all' ? UC.allSteps : (STEPS[k] || {}).label;
      cap = (selected ? 'Showing step: ' : 'Following the replay: ') + '<b>' + esc(lbl) + '</b>' + (names.length ? ' · lit: ' + esc(names.join(', ')) : ' · nothing runs in this step for this journey') + (selected ? ' · <a href="#" data-step="follow">Follow the replay</a>' : '');
    }
    var hot = S.step === null && S.play ? hotLayers(v).hot : {};
    $$('.dn', svg).forEach(function (g) { var id = g.dataset.node; g.classList.toggle('on', !!on[id]); g.classList.toggle('hot', !!(hot[id] || (id === 'api' && hot.L6))); });
    $$('.de', svg).forEach(function (p) { var e = p.dataset.e.split('-'); p.classList.toggle('on', !!(on[e[0]] && on[e[1]])); });
    if ($('#dcap').innerHTML !== cap) $('#dcap').innerHTML = cap;
    var P = planOf(v), DT = UD.decomposition || {}, tree = P ? '<h3>' + esc(DT.heading) + '</h3><p class="small">' + esc(DT.intro) + '</p>' + sfViews() : '';
    var legacy = !P && v && (v.milestones || []).some(function (m) { return m.name === 'SentToOSS' && !(m.body || {}).via; });
    if (legacy) tree = '<p class="note fallback"><b>' + esc(DT.fallbackRoute || 'fallback route') + '</b>: this recorded run sent the order to the legacy OSS stand-in, not through Salesforce order orchestration. The live workflow no longer falls back: with no fulfilment plan it stops with a clear error.</p>';
    if ($('#dtree').dataset.k !== tree) { $('#dtree').innerHTML = tree; $('#dtree').dataset.k = tree; $('#dtree').hidden = !tree; }
  }

  /* ---------- 3. How it's built: step timeline on the left, what each layer did in that step on the right ---------- */
  function shellArchitect() {
    var g = COPY.glossary || [], M = UA.mapping || [];
    $('#v-architect').innerHTML = '<div class="av3"><div class="agrid3"><aside class="panel atl" id="atl"></aside><div class="alay" id="alay"></div></div>' +
      '<p class="sorline"><b>All system-of-record access is through TM Forum Open APIs exposed by Salesforce; no Salesforce-specific APIs above the systems layer.</b></p>' +
      exposedApis() +
      '<div class="ph boxh"><h2>' + esc(UA.mappingHeading) + '</h2><span class="lab mix">conceptual alignment</span></div><div class="panel boxb" id="oda"><p class="small">' + esc(UA.mappingIntro) + '</p><p>' + esc(UA.etom) + '</p>' +
      '<table class="t"><tr><th>Step in the journey</th><th>TM Forum Open API</th><th>ODA functional block (conceptual)</th><th>SID entities (inferred)</th></tr>' + M.map(function (r) { return '<tr><td>' + esc(r[0]) + '</td><td><span class="tmf"><b>' + esc(r[1].split(' ')[0]) + '</b> ' + esc(r[1].split(' ').slice(1).join(' ')) + '</span></td><td>' + esc(r[2]) + '</td><td class="small">' + esc(r[3]) + '</td></tr>'; }).join('') + '</table></div>' +
      '<div class="ph boxh"><h2>Glossary (' + g.length + ' terms, from docs/mvp/layer-panels.md)</h2><input class="glf" id="glf" placeholder="Filter terms…"></div>' +
      '<div class="panel boxb"><div class="gl" id="gl"></div></div></div>';
    var draw = function (f) { $('#gl').innerHTML = g.filter(function (x) { return !f || (x.term + x.definition).toLowerCase().indexOf(f) >= 0; }).map(function (x) { return '<div class="gt"><b>' + esc(x.term) + '</b> · ' + esc(x.definition) + '</div>'; }).join(''); };
    draw(''); $('#glf').oninput = function () { draw(this.value.toLowerCase()); };
  }
  var archKey = '';
  function winView(k) {   // the run as it stood at the end of step k (or now, if the replay is still inside it), keeping only what happened in the step
    var W = windows(S.full), w = k === 'all' ? { a: -Infinity, b: Infinity } : W[k], t = nowT();
    var tc = Math.min(t, w.b === Infinity ? Infinity : w.b - 1), vEnd = view(S.full, tc === Infinity && !LIVE ? Infinity : tc);
    var f = function (x) { return T(x) >= w.a; }, s = Object.assign({}, vEnd);
    ['messages', 'decisions', 'consent', 'milestones', 'jeopardy'].forEach(function (n) { s[n] = (vEnd[n] || []).filter(function (x) { return f(x.at); }); });
    s.spans = vEnd.spans.filter(function (x) { return f(x.start_ts); });
    s.reports = (vEnd.reports || []).filter(function (r) { return f(r.creationDate); });
    s.bpmn = (vEnd.bpmn || []).filter(function (a) { return f(a.start); });
    s.intentHere = !!(vEnd.intent && f(vEnd.intent.body && vEnd.intent.body.creationDate));
    return { w: s, end: vEnd, reached: w.a0 == null ? (k === 'all') : w.a0 <= t };
  }
  function renderArchitect(v) {
    var W = windows(S.full), k = selStep(), kinds = stepKinds(v);
    var key = [S.caseId, k, v ? v.spans.length : 0, v ? v.spans.filter(function (s) { return s.running; }).length : 0, v ? (v.bpmn || []).map(function (a) { return a.end ? 1 : 0; }).join('') : '', v ? v.messages.length + ':' + v.milestones.length : ''].join('|');
    if (key === archKey) return; archKey = key;
    var atl = $('#atl'), al = $('#alay');
    if (!v || !W) {
      atl.innerHTML = '<h3>' + esc(UA.stepsHeading) + '</h3><p class="small">Choose a journey in What changes for the business (or press 1 to 4), then Play.</p>';
      al.innerHTML = '<h3>' + esc(UA.layersHeading) + '</h3>' + LAYER_IDS.map(function (id) { return layerSec(id, '', true); }).join('');
      return;
    }
    atl.innerHTML = '<h3>' + esc(UA.stepsHeading) + ' <span class="small">(UK time)</span></h3>' +
      '<button class="as all' + (k === 'all' ? ' sel' : '') + '" data-step="all"><b>' + esc(UC.allSteps) + '</b><span>' + v.spans.length + ' logged steps so far</span></button>' +
      kinds.map(function (c, i) {
        var w = W[i], sp = w.a == null ? [] : v.spans.filter(function (s) { var t = T(s.start_ts); return t >= w.a && t < w.b; });
        var lays = {}; sp.forEach(function (s) { lays[s.layer] = 1; });
        var rng = w.a0 == null ? 'not in this journey' : hm(w.a0) + (w.b !== Infinity ? ' – ' + hm(w.b) : '');
        var head = '<button class="as ' + c.k + (k === i ? ' sel' : '') + '" data-step="' + i + '"><b>' + (i + 1) + '. ' + esc(c.b) + '</b><span>' + esc(rng) + (sp.length ? ' · ' + sp.length + ' entries · ' + Object.keys(lays).sort().join(' ') : '') + '</span></button>';
        if (k !== i || !sp.length) return head;
        return head + '<table class="t asp">' + sp.slice().sort(byStart).map(function (s) { return '<tr' + (isCall(s) ? ' class="call" data-sid="' + esc(s.span_id) + '" tabindex="0" title="Open the request and response"' : '') + '><td><span class="lyn" style="--c:var(--' + s.layer.toLowerCase() + ')">' + s.layer + '</span></td><td>' + esc(s.step) + (/^Legacy OSS/.test(s.step) ? ' <span class="lab mock">' + esc((UD.decomposition || {}).fallbackRoute || 'fallback route') + '</span>' : '') + '</td><td class="small">' + ms(s) + '</td></tr>'; }).join('') + '</table>';
      }).join('');
    if (k == null) { al.innerHTML = '<h3>' + esc(UA.layersHeading) + '</h3><p class="small">Press Play, or pick a step on the left.</p>'; return; }
    var wv = winView(k), lbl = k === 'all' ? UC.allSteps : (STEPS[k] || {}).label;
    al.innerHTML = '<h3>' + esc(UA.layersHeading) + ' · <span class="stp">' + esc(lbl) + '</span></h3>' + (k !== 'all' && W[k].a == null ? '<p class="note">' + esc(UA.notInJourney) + '</p>' : wv.reached ? '' : '<p class="note">' + esc(UA.notReached) + '</p>') +
      LAYER_IDS.map(function (id) { return layerSec(id, '', true); }).join('');
    LAYER_IDS.forEach(function (id) {
      var box = $('.lsec[data-layer="' + id + '"] .lb', al), used = wv.reached && ARCH[id](box, wv.w, wv.end, k);
      $('.lsec[data-layer="' + id + '"]', al).classList.toggle('idle', !used);
      if (!used) box.innerHTML = '<p class="small">' + esc(wv.reached || W[k] && W[k].a == null ? UA.notUsed : UA.notReached) + '</p>';
    });
  }
  function layerSec(id) {
    var l = layerCopy[id] || {}, sk = statusKind(l.status);
    return '<section class="lsec" data-layer="' + id + '" style="--c:var(--' + id.toLowerCase() + ')"><div class="lh"><span class="n">' + id + '</span><b>' + esc(l.name) + '</b><span class="q">' + esc(l.question) + '</span><span class="lab ' + sk[0] + '" title="' + esc(l.status) + '">' + sk[1] + '</span><button class="tb sm" data-about="' + id + '">' + esc(UA.about) + '</button></div><div class="lb"></div></section>';
  }
  function quote(m) { return '<blockquote class="q2">' + linkify(m.content) + '<span class="small"> · ' + hm(T(m.at)) + '</span></blockquote>'; }
  function orchPanels(P) {
    var so = P.serviceOrder || {}, DT = UD.decomposition || {}, PI = P.productInventory || {}, NF = so.networkFulfilment || {};
    return sfViews() +
      (so.id ? '<p>TMF641 service order <b class="mono">' + esc(so.id) + '</b>: ' + esc((so.stateChange || []).map(function (c) { return c.state; }).join(' → ') || so.state || '') + ' · ' + (so.items || []).map(function (i) { return esc(i.service) + ' ' + actChip(i.action); }).join(' · ') + '</p>' : '') +
      (NF.reservation || NF.serviceInventory ? '<p class="small">Network side (inside the mocked network, not called by Salesforce): ' + [NF.reservation ? esc(NF.reservation.api) + ' reservation ' + esc(NF.reservation.id || '') : '', NF.serviceInventory ? esc(NF.serviceInventory.api) + ' services updated' : '', NF.resourceInventory ? esc(NF.resourceInventory.api) + ' resources updated' : ''].filter(Boolean).join(' · ') + ', returned as data in the TMF641 response.</p>' : '') +
      (PI.writer ? '<p class="small">' + esc(DT.assetStep || 'Assetisation done (TMF637)') + '</p>' : '') +
      '<p class="small">Idempotency key <span class="mono">' + esc(P.idempotencyKey || '') + '</span> (the order) · network order adapter: ' + esc(P.adapterMode || '') + '. ' + SIM_SENTENCE + '</p>';
  }
  var ARCH = {
    L1: function (b, w, e) {
      var sp = w.spans.filter(function (s) { return s.layer === 'L1'; }), um = w.messages.filter(function (m) { return m.role === 'user'; });
      if (!sp.length && !w.reports.length && !w.consent.length) return false;
      var h = um.length ? '<div class="sec">Customer said</div>' + um.map(quote).join('') : '';
      if (w.consent.length) h += '<div class="sec">Customer go-ahead</div>' + w.consent.map(function (c) { return '<p>“' + esc(c.text) + '” · ' + hm(T(c.at)) + '</p>'; }).join('');
      var it = e.intent;
      if (it && w.intentHere) { var ex = (it.body.expression || {}).expressionValue || it.body.expression; h += '<div class="sec">Intent [TMF921], recorded in this step</div><p><b>' + esc(it.id) + '</b> · ' + esc(it.body.name || '') + '</p><pre class="js">' + esc(JSON.stringify(ex, null, 1)) + '</pre>'; }
      else if (it) h += '<p class="small">Intent <b>' + esc(it.id) + '</b> · lifecycle ' + esc(it.lifecycle_status) + '</p>';
      if (w.reports.length) h += '<div class="sec">Intent reports</div>' + spanRows(w.reports, [['When', function (r) { return hm(T(r.creationDate)); }], ['Report', function (r) { return esc(r.name); }], ['State', function (r) { var s = r.expression.expressionValue['icm:reportState']; return '<span class="lab ' + (/Complies/.test(s) ? 'real' : 'mock') + '">' + esc(s.replace('icm:', '')) + '</span>'; }], ['Detail', function (r) { var x = r.expression.expressionValue; return esc(x.reason || x.product || '') + (x.revisedCompletionDate ? ' · revised ' + esc(x.revisedCompletionDate) : ''); }]]);
      var other = sp.filter(function (s) { return !/Customer message/.test(s.step); });
      if (other.length) h += '<div class="sec">Steps</div>' + spanRows(other, [['Step', function (s) { return esc(s.step); }], ['Time', ms]]);
      b.innerHTML = h; return true;
    },
    L2: function (b, w) {
      var sp = w.spans.filter(function (s) { return s.layer === 'L2'; }); if (!sp.length) return false;
      var model = sp.filter(function (s) { return /Model call/.test(s.step); }), tin = 0, tout = 0; model.forEach(function (s) { tin += (s.attributes || {}).promptTokens || 0; tout += (s.attributes || {}).outputTokens || 0; });
      var am = w.messages.filter(function (m) { return m.role === 'assistant'; });
      b.innerHTML = '<p>' + (model.length ? model.length + ' model calls · ' + tin + ' prompt tokens · ' + tout + ' output tokens in this step. ' : '') + 'The agent proposes only: it reads through tools and has no tool that writes to Salesforce.</p>' +
        spanRows(sp, [['Step', function (s) { return esc(s.step); }], ['Tools called', function (s) { return esc(((s.attributes || {}).toolCalls || []).join(', ')); }], ['Time', ms]]) +
        (am.length ? '<div class="sec">Agent said</div>' + am.map(quote).join('') : '');
      return true;
    },
    L3: function (b, w, e) {
      if (!w.spans.length) return false;
      var st = e.state || {}, L = e.links || {}, ids = [['Conversation', e.conversation.id || e.conversation.conversation_id || ''], ['Trace', e.conversation.trace_id]];
      if (e.intent) ids.push(['Intent (TMF921)', e.intent.id], ['Order business key', st.orderExternalId]);
      if (e.bpmn && e.bpmn.length) ids.push(['Workflow process instance', st.processInstanceId]);
      if ((e.milestones || []).some(function (m) { return m.name === 'OrderInProgress'; })) ids.push(['Salesforce order', '<a class="link" target="_blank" rel="noopener" href="' + esc(L.order) + '">' + esc(maskNum('Order ' + (L.orderNumber || ''))) + '</a>']);
      var resolved = w.spans.some(function (s) { return s.layer === 'L3'; });
      b.innerHTML = '<div class="sec">Audit entries in this step (' + w.spans.length + ')</div>' +
        '<div class="scroll">' + spanRows(w.spans.slice().sort(byStart), [['Layer', function (s) { return '<span class="lyn" style="--c:var(--' + s.layer.toLowerCase() + ')">' + s.layer + '</span>'; }], ['Step', function (s) { return esc(s.step); }], ['Span ID', function (s) { return '<span class="mono">' + esc(s.span_id) + '</span>'; }], ['Parent', function (s) { return '<span class="mono small">' + esc(s.parent_span_id || '—') + '</span>'; }]]) + '</div>' +
        '<div class="sec">IDs matched across systems</div>' + spanRows(ids.filter(function (x) { return x[1]; }), [['What', function (x) { return x[0]; }], ['ID', function (x) { return /^</.test(x[1]) ? x[1] : '<span class="mono">' + esc(x[1]) + '</span>'; }]]) +
        '<div class="sec">Same customer in each system' + (resolved ? ' (resolved in this step)' : '') + '</div>' +
        spanRows(e.xref || [], [['System', function (x) { return '<b>' + esc(x.system) + '</b>'; }], ['ID', function (x) { return '<span class="mono">' + esc(x.external_id) + '</span>'; }], ['Source', function (x) { return '<span class="small">' + esc(x.source) + '</span>'; }], ['Verified', function (x) { return x.verified ? '<span class="ok">✔</span>' : '✖'; }]]) +
        '<p class="small">Every entry carries the same trace ID; span and parent IDs link each step to the one that caused it. IDs are examples from the demo org and stand-ins.</p>';
      return true;
    },
    L4: function (b, w, e) {
      if (!w.spans.some(function (s) { return s.layer === 'L4'; }) && !w.decisions.length) return false;
      RENDER.L4(b, w);
      var packs = w.spans.filter(function (s) { return s.layer === 'L4' && /context pack/i.test(s.step); });
      var reads = w.spans.filter(function (s) { return s.layer === 'L6' && isCall(s) && packs.some(function (p) { return s.parent_span_id === p.span_id || (T(s.start_ts) >= T(p.start_ts) && T(s.start_ts) <= T(p.end_ts)); }); });
      if (reads.length) b.insertAdjacentHTML('beforeend', '<div class="sec">Sources: TMF reads behind the context pack (' + reads.length + ')</div>' + apiRows(reads, e, false));
      return true;
    },
    L5: function (b, w, e) {
      if (!w.spans.some(function (s) { return s.layer === 'L5'; }) && !w.bpmn.length) return false;
      var here = {}; w.bpmn.forEach(function (a) { here[a.id + a.start] = 1; });
      var acts = (e.bpmn || []).map(function (a) { return Object.assign({}, a, { mark: here[a.id + a.start] ? (a.end ? 'stp' : 'cur') : 'done' }); });
      b.innerHTML = '<div class="bpmn" id="bpmna"></div><p class="small"><span class="chip ours">done earlier</span><span class="chip sf">this step</span><span class="chip st">jeopardy</span> · business key <span class="mono">' + esc((e.state || {}).orderExternalId || '—') + '</span></p>' +
        (w.bpmn.length ? spanRows(w.bpmn.filter(function (a) { return a.type !== 'sequenceFlow'; }), [['Started', function (a) { return hm(T(a.start)); }], ['BPMN step', function (a) { return esc(a.name || a.id); }], ['Type', function (a) { return '<span class="small">' + esc(a.type) + '</span>'; }], ['State', function (a) { return a.end ? '<span class="ok">done</span>' : '<b style="color:var(--l5)">current</b>'; }]]) : '');
      drawBpmn($('#bpmna', b), acts);
      return true;
    },
    L6: function (b, w, e) {
      var calls = w.spans.filter(function (s) { return s.layer === 'L6'; }); if (!calls.length) return false;
      b.innerHTML = '<p><span class="chip sf">' + SF_CHIP + '</span><span class="chip st">' + STANDIN_CHIP + '</span>' + (calls.some(function (s) { return /network order adapter/i.test(s.runtime || ''); }) ? '<span class="chip st">' + NET_CHIP + '</span>' : '') + ' <span class="small">Click a call to see its TMF request and response.</span></p>' + apiRows(calls, e, true);
      var P = planOf(w);
      if (P) b.insertAdjacentHTML('beforeend', orchPanels(P));
      return true;
    },
    L7: function (b, w, e) {
      if (!w.milestones.some(function (m) { return /SentToOSS|PortReserved|Jeopardy|Live/.test(m.name); }) && !w.jeopardy.length) return false;
      RENDER.L7(b, e); return true;
    },
    L8: function (b, w) { if (!w.spans.length) return false; RENDER.L8(b, w); return true; }
  };

  /* ---------- layer detail drawer ---------- */
  function openLayer(id, auto) { S.open = id; if (!auto) S.follow = false; var d = $('#drawer'); d.classList.add('open'); d.setAttribute('aria-hidden', 'false'); d.style.setProperty('--c', 'var(--' + id.toLowerCase() + ')'); d.dataset.k = ''; renderLayer(id, view(S.full, S.t)); }
  function closeLayer() { S.open = null; S.follow = false; var d = $('#drawer'); d.classList.remove('open'); d.setAttribute('aria-hidden', 'true'); }
  var bpmnViewer = null, bpmnLoaded = null;
  function renderLayer(id, v) {
    var l = layerCopy[id] || {}, d = $('#drawer'), k = statusKind(l.status);
    var sig = id + '|' + (v ? v.spans.length + ':' + v.messages.length + ':' + (v.milestones || []).length + ':' + (v.bpmn || []).map(function (a) { return a.end ? 1 : 0; }).join('') + ':' + v.spans.filter(function (s) { return s.running; }).length : 0);
    if (d.dataset.k === sig) return; d.dataset.k = sig;
    var keepScroll = $('.db', d) ? $('.db', d).scrollTop : 0;
    d.innerHTML = '<div class="dh"><span class="n">' + id + '</span><div><h3>' + esc(l.name) + '</h3><div class="q">' + esc(l.question) + '</div><div style="margin-top:4px"><span class="lab ' + k[0] + '">' + esc(l.status) + '</span> <span class="small">' + esc(l.label) + '</span></div></div><button class="x" aria-label="Close">×</button></div>' +
      '<div class="db">' + (l.body || []).map(function (p) { return '<p>' + esc(p) + '</p>'; }).join('') +
      (l.bullets && l.bullets.length ? '<ul class="bul">' + l.bullets.map(function (b) { return '<li>' + (b.key ? '<b>' + esc(b.key) + ':</b> ' : '') + esc(b.text) + '</li>'; }).join('') + '</ul>' : '') +
      '<div class="sec">For this run ' + (LIVE ? '<span class="lab real">live data</span>' : '<span class="lab mix">recorded run</span>') + '</div><div id="ld"></div></div>';
    $('.x', d).onclick = closeLayer;
    var box = $('#ld', d);
    if (!v) { box.innerHTML = '<p class="small">Start a case to see what this layer does for the request.</p>'; return; }
    (RENDER[id] || function () { })(box, v);
    var own = id === 'L6' || id === 'L8' ? [] : v.spans.filter(function (s) { return s.layer === id && isCall(s); });
    if (id === 'L4') {   // the TMF reads behind each context pack (L6 calls made while the pack was being built)
      var packs = v.spans.filter(function (s) { return s.layer === 'L4' && /context pack/i.test(s.step); });
      var reads = v.spans.filter(function (s) {
        return s.layer === 'L6' && isCall(s) && packs.some(function (p) { return s.parent_span_id === p.span_id || (T(s.start_ts) >= T(p.start_ts) && T(s.start_ts) <= T(p.end_ts)); });
      });
      if (reads.length) box.insertAdjacentHTML('beforeend', '<div class="sec">TMF reads behind the context pack (' + reads.length + ')</div><div id="l4reads">' + apiRows(reads, v, false) + '</div>');
    }
    if (own.length) box.insertAdjacentHTML('beforeend', '<div class="sec">API calls from this layer (' + own.length + ')</div>' + apiRows(own, v, false));
    $('.db', d).scrollTop = keepScroll;
  }
  function spanRows(list, cols) { return '<table class="t"><tr>' + cols.map(function (c) { return '<th>' + c[0] + '</th>'; }).join('') + '</tr>' + list.map(function (s) { return '<tr>' + cols.map(function (c) { return '<td>' + c[1](s) + '</td>'; }).join('') + '</tr>'; }).join('') + '</table>'; }
  function ms(s) { return s.running ? '<span class="warn">running…</span>' : (s.duration_ms >= 1000 ? (s.duration_ms / 1000).toFixed(1) + ' s' : Math.round(s.duration_ms) + ' ms'); }
  /* Every Salesforce call reads 'TMF Open API'; who provides it (out of the box or the TMF facade) is shown in the call detail only.
     Recordings made before the chip rename carry 'TMF Open API (Salesforce)' and show the same chip. */
  var SF_CHIP = 'TMF Open API', STANDIN_CHIP = 'Legacy stand-in (mocked)', NET_CHIP = 'Network order adapter (Mocked)';
  function isSfRt(r) { return /^TMF Open API( \(Salesforce\))?$/.test(r || ''); }
  function rtChip(s) { var r = s.runtime || ''; if (isSfRt(r)) return '<span class="chip sf">' + SF_CHIP + '</span>'; if (/network order adapter/i.test(r)) return '<span class="chip st">' + NET_CHIP + '</span>'; if (/stand-in/i.test(r)) return '<span class="chip st">' + STANDIN_CHIP + '</span>'; return '<span class="chip ours">' + esc(rtName(r)) + '</span>'; }
  /* Salesforce order orchestration: the compact x-orchestration the workflow recorded when the plan completed (FulfilmentPlan milestone) */
  var SIM_SENTENCE = 'The TMF641 request and response are simulated inside Salesforce for this demo.';
  function planOf(v) { var m = ((v && v.milestones) || []).filter(function (x) { return x.name === 'FulfilmentPlan'; }).pop(); return m ? m.body || {} : null; }
  function actChip(a) { return '<span class="act act-' + esc(String(a || '').toLowerCase()) + '">' + esc(a || '—') + '</span>'; }
  // Salesforce's own screens (evidence gallery captures): the native decomposition view and the whole orchestration plan.
  function sfShot(re) { return (CFG.evidence || []).filter(function (e) { return re.test(e.file); })[0]; }
  function sfViews() {
    var DT = UD.decomposition || {}, shots = [[/decomposition/, DT.decompositionShot || 'Decomposition'], [/fulfilment-plan/, DT.planShot || 'Orchestration plan']];
    return shots.map(function (x) {
      var e = sfShot(x[0]); if (!e) return '';
      return '<div class="sec">' + esc(x[1]) + '</div><figure class="sfshot"><img src="' + e.src + '" alt="' + esc(e.caption) + '" loading="lazy"><figcaption class="small">' + esc(e.caption) + '</figcaption></figure>';
    }).join('') + '<p class="small codesnote">' + esc(DT.screensNote || '') + '</p>';
  }
  function tmfTag(s) { var m = String(s.api || '').match(/^(TMF\d+)\s*(.*)$/); return m ? '<span class="tmf"><b>' + esc(m[1]) + '</b> ' + esc(m[2]) + '</span>' : '<span class="mono small">' + esc(/ollama/i.test(s.api || '') ? 'Model API' : (s.api || '')) + '</span>'; }
  function shortPath(p) { return String(p || '').replace(/^\/services\/apexrest\/agentictelco/, '…/apexrest/agentictelco').replace(/^\/services\/data\/v\d+\.\d+\/connect\/comms/, '…/connect/comms'); }
  function isCall(s) { return s.method && s.path; }
  function apiRows(list, v, extra) {
    return '<table class="t api"><tr><th>Time</th><th>Step</th><th>Method · path</th><th>TMF API</th><th>Runs as</th><th>Status</th>' + (extra ? '<th>Record</th>' : '') + '</tr>' + list.map(function (s) {
      return '<tr class="call" data-sid="' + esc(s.span_id) + '" tabindex="0" title="Open the request and response"><td>' + hm(T(s.start_ts)) + '</td><td>' + esc(s.step) + '<div class="small">' + esc(s.component) + '</div></td>' +
        '<td><span class="mth">' + esc(s.method) + '</span> <span class="mono small">' + esc(shortPath(s.path)) + '</span></td><td>' + tmfTag(s) + '</td><td>' + rtChip(s) + '</td><td>' + (s.running ? '…' : esc(s.status)) + '</td>' + (extra ? '<td>' + linkFor(s, v) + '</td>' : '') + '</tr>';
    }).join('') + '</table>';
  }
  /* client-side redaction as well (the gateway and the build already redact): no tokens, session ids, login or instance URLs */
  var SECRET_KEY = /^(?:(?:access|refresh|id|bearer|api)?_?token|session_?id|sid|(?:set-)?cookie)$|authori[sz]ation|password|secret|frontdoor/i;
  function redact(x) {
    if (Array.isArray(x)) return x.map(redact);
    if (x && typeof x === 'object') { var o = {}; Object.keys(x).forEach(function (k) { o[k] = SECRET_KEY.test(k) ? '[redacted]' : redact(x[k]); }); return o; }
    if (typeof x === 'string') return x.replace(/\b00D[A-Za-z0-9]{12,15}![A-Za-z0-9._-]+/g, '[redacted]').replace(/https?:\/\/[A-Za-z0-9.-]+\.(?:my\.)?(?:salesforce|force|cloudforce|salesforce-setup|visualforce)\.com[^\s"']*/g, function (u) { return /\/lightning\/r\//.test(u) && !/frontdoor|sid=/.test(u) ? u : '[instance]' + u.replace(/^https?:\/\/[^\/]+/, '').split('?')[0]; });
    return x;
  }
  function providedBy(s) { var a = s.attributes || {}; if (a.providedBy) return a.providedBy; return /apexrest\/agentictelco/.test(s.path || '') ? 'TMF facade within Salesforce (Apex)' : /connect\/comms/.test(s.path || '') ? 'Salesforce (out of the box)' : /stand-in/i.test(s.runtime || '') ? STANDIN_CHIP : /network order adapter/i.test(s.runtime || '') ? 'Salesforce order orchestration, through the network order adapter (Mocked: simulated inside Salesforce for this demo)' : rtName(s.runtime); }
  function openCall(sid) {
    var v = view(S.full, S.t) || S.full; if (!v) return;
    var s = (v.spans || []).filter(function (x) { return x.span_id === sid; })[0]; if (!s) return;
    var d = $('#calld'); if (!d) { d = document.createElement('div'); d.id = 'calld'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-modal', 'true'); document.body.appendChild(d); }
    var link = linkFor(s, v), J = function (o) { return o == null ? '—' : esc(maskNum(JSON.stringify(redact(o), null, 1))); };
    d.innerHTML = '<div class="cd"><div class="cdh"><div><div class="small">' + esc(s.layer) + ' · ' + esc(s.component) + '</div><h3>' + esc(s.step) + '</h3>' +
      '<div>' + tmfTag(s) + ' ' + rtChip(s) + '</div></div><button class="x" aria-label="Close">×</button></div>' +
      '<div class="cdb"><p><span class="mth">' + esc(s.method) + '</span> <span class="mono">' + esc(s.path) + '</span></p>' +
      '<p class="pby">Provided by: <b>' + esc(providedBy(s)) + '</b></p>' +
      '<p>Status <b>' + (s.running ? 'running…' : esc(s.status)) + '</b> · ' + ms(s) + (link ? ' · Salesforce record: ' + link : '') + '</p>' +
      '<div class="sec">Request</div><pre class="js">' + J(s.request) + '</pre><div class="sec">Response</div><pre class="js">' + J(s.response) + '</pre>' +
      '<p class="small">Redacted: no tokens, session IDs or instance login URLs. Long bodies are shortened in the recorded runs. Record links open Salesforce and need your own login.</p></div></div>';
    d.classList.add('open');
    var close = function () { d.classList.remove('open'); };
    $('.x', d).onclick = close; d.onclick = function (e) { if (e.target === d) close(); };
    $('.x', d).focus();
  }
  document.addEventListener('click', function (e) { var r = e.target.closest && e.target.closest('tr.call'); if (r && !(e.target.closest('a'))) openCall(r.dataset.sid); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && $('#calld')) $('#calld').classList.remove('open'); if (e.key === 'Enter' && e.target.matches && e.target.matches('tr.call')) openCall(e.target.dataset.sid); });
  function linkFor(s, v) {
    var L = v.links || {}, ms_ = v.milestones || [], has = function (n) { return ms_.some(function (m) { return m.name === n; }); }, a = function (u, t) { return u ? '<a class="link" target="_blank" rel="noopener" href="' + esc(u) + '">' + t + '</a>' : ''; };
    if (/Create quote/.test(s.step) && has('QuoteCreated')) return a(L.quote, 'Quote');
    if (/Place upgrade order|Order in progress|Complete order/.test(s.step) && has('OrderInProgress')) return a(L.order, maskNum('Order ' + (L.orderNumber || '')));
    if (/Create Fibre 900/.test(s.step) && has('AssetChanged')) return a(L.newAsset, 'Fibre 900 asset');
    if (/productRelationship/.test(s.step) && has('AssetChanged')) return a(L.relationship, 'Upgrade link');
    if (/Fibre 150 terminated|Read current installed (service|product)|^Installed (service|product)/.test(s.step)) return a(L.oldAsset, 'Fibre 150 asset');
    if (/^Customer$|Organization and contact roles|Contact role on the account|Who can order/.test(s.step)) return a(L.account, 'Account');
    return '';
  }
  function portIs900(v) { return (v.milestones || []).some(function (m) { return m.name === 'PortReserved' || m.name === 'Live'; }); }
  var RENDER = {
    L1: function (b, v) {
      var it = v.intent;
      var h = '<div class="sec">Intent [TMF921]</div>';
      if (!it) h += '<p class="small">No Intent yet. The agent records an Intent only when the customer agrees (and the advisory policy check allows it).</p>';
      else { var e = (it.body.expression || {}).expressionValue || it.body.expression; h += '<p><b>' + esc(it.id) + '</b> · lifecycle <span class="lab ' + (it.lifecycle_status === 'fulfilled' ? 'real' : it.lifecycle_status === 'atRisk' ? 'mock' : 'mix') + '">' + esc(it.lifecycle_status) + '</span> · ' + esc(it.body.name || '') + '</p><pre class="js">' + esc(JSON.stringify(e, null, 1)) + '</pre>'; }
      h += '<div class="sec">Intent reports</div>' + ((v.reports || []).length ? spanRows(v.reports, [['When', function (r) { return hm(T(r.creationDate)); }], ['Report', function (r) { return esc(r.name); }], ['State', function (r) { var s = r.expression.expressionValue['icm:reportState']; return '<span class="lab ' + (/Complies/.test(s) ? 'real' : 'mock') + '">' + esc(s.replace('icm:', '')) + '</span>'; }], ['Detail', function (r) { var x = r.expression.expressionValue; return esc(x.reason || x.product || '') + (x.revisedCompletionDate ? ' · revised ' + esc(x.revisedCompletionDate) : ''); }]]) : '<p class="small">None yet.</p>');
      h += '<div class="sec">Customer go-ahead</div>' + (v.consent.length ? v.consent.map(function (c) { return '<p>“' + esc(c.text) + '” · ' + hm(T(c.at)) + '</p>'; }).join('') : '<p class="small">No go-ahead recorded.</p>');
      b.innerHTML = h;
    },
    L2: function (b, v) {
      var calls = v.spans.filter(function (s) { return s.layer === 'L2'; }), model = calls.filter(function (s) { return /Model call/.test(s.step); });
      var tin = 0, tout = 0; model.forEach(function (s) { tin += (s.attributes || {}).promptTokens || 0; tout += (s.attributes || {}).outputTokens || 0; });
      b.innerHTML = '<p>' + model.length + ' model calls · ' + tin + ' prompt tokens · ' + tout + ' output tokens (measured this run).</p>' +
        '<p class="small">The agent only proposes. It reads the context pack through MCP tools and records an Intent; it has no tool that writes to Salesforce.</p>' +
        spanRows(calls, [['Step', function (s) { return esc(s.step); }], ['Tools', function (s) { var a = s.attributes || {}; return esc((a.toolCalls || []).join(', ')); }], ['Time', ms]]);
    },
    L3: function (b, v) {
      b.innerHTML = '<div class="sec">Cross-reference: the same customer in each system</div>' +
        spanRows(v.xref || [], [['System', function (x) { return '<b>' + esc(x.system) + '</b>'; }], ['ID', function (x) { return '<span class="mono">' + esc(x.external_id) + '</span>'; }], ['Source', function (x) { return '<span class="small">' + esc(x.source) + '</span>'; }], ['Verified', function (x) { return x.verified ? '<span class="ok">✔</span>' : '✖'; }]]) +
        '<div class="sec">What we remember for this conversation</div><p>' + v.messages.length + ' messages · ' + v.decisions.length + ' policy decisions · ' + v.consent.length + ' customer go-ahead · ' + v.spans.length + ' audit rows (trace <span class="mono">' + esc(v.conversation.trace_id) + '</span>)</p>' +
        '<p class="small">IDs are examples from the demo org and stand-ins.</p>';
    },
    L4: function (b, v) {
      var pack = (v.state || {}).contextPack, h = '';
      if (!v.spans.some(function (s) { return s.layer === 'L4'; })) pack = null;
      h += '<div class="sec">Context pack (with sources)</div>';
      if (!pack) h += '<p class="small">Not built yet.</p>';
      else {
        var items = [];
        Object.keys(pack).forEach(function (k) {
          var x = pack[k]; if (k === 'offerings' || x == null) return;
          var val = typeof x !== 'object' ? x : (x.value !== undefined ? x.value : (x.name || x.fullName || ''));
          if (k === 'requester') val = x.fullName + ' · ' + x.role + (x.authorisedContact ? ' (authorised)' : ' (not authorised)');
          if (k === 'currentBroadband') val = (x.product || x.name) + ' · £' + x.monthlyPriceGBP + '/month';
          if (k === 'promotions') val = (x.applicable && x.applicable.length ? x.applicable.join(', ') : 'none applicable') + ' · ' + (typeof x.activeInOrg === 'number' ? x.activeInOrg : (x.activeInOrg || []).length) + ' active in org';
          if (k === 'contractMonthsLeft') val = x.value + ' months left · ends ' + x.contractEnd;
          if (k === 'sizing') val = x.staffOnVideoCalls + ' people × ' + x.mbpsPerPerson + ' Mbps = ' + x.neededMbps + ' Mbps → ' + x.bestFitName + ' (' + x.mbpsPerPerson + ' Mbps per video user is our sizing assumption)';
          if (Array.isArray(val)) val = val.map(function (y) { return typeof y === 'object' ? (y.name || JSON.stringify(y)) : y; }).join(', ');
          if (typeof val === 'object') val = JSON.stringify(val);
          if (typeof val === 'boolean') val = val ? 'yes' : 'no';
          var src = x.src || x.source || '';
          var ch = /salesforce/i.test(src) ? 'sf' : /stand-in|billing|availab|legacy/i.test(src) ? 'st' : /L3|identity/i.test(src) ? 'l3' : 'ours';
          var shown = ch === 'sf' ? SF_CHIP + ' · ' + src.replace(/^salesforce:/, '') : src;
          items.push('<div class="pk"><b>' + esc(k) + '</b>' + esc(val) + (src ? '<div><span class="chip ' + ch + '">' + esc(shown) + '</span></div>' : '') + '</div>');
        });
        h += '<div class="pack">' + items.join('') + '</div>';
      }
      h += '<div class="sec">Policy decisions (OPA, ' + esc((v.decisions[0] || {}).policy_version || 'mvp-2026-10-30.1') + ')</div>';
      var off = {}; ((pack || {}).offerings || []).forEach(function (o) { off[o.id] = o.name; });
      h += v.decisions.length ? v.decisions.map(function (d) {
        var r = d.result, to = (d.input.proposal || {}).to;
        return '<div class="dec ' + (r.allow ? 'allow' : 'deny') + '"><b>' + (d.mode === 'binding' ? 'Binding (L5 workflow)' : 'Advisory (L4 context)') + '</b> · ' + esc(off[to] || to) + ' → ' + (r.allow ? '<span class="ok">allow</span>' : '<span class="err">deny</span>') + (r.reasons && r.reasons.length ? ' · ' + esc(r.reasons.join(' ')) : '') + ' <span class="small">' + hm(T(d.at)) + '</span></div>';
      }).join('') : '<p class="small">No decision yet.</p>';
      var hit = {}; v.decisions.forEach(function (d) { (d.result.deny || []).forEach(function (x) { if (d.mode === 'advisory' && x === 'not_available_at_site') return; hit[x] = 1; }); });
      h += '<div class="sec">The rule (one versioned policy, upgrade.rego)</div>' + REGO.split('\n').filter(function (x) { return /^deny contains/.test(x); }).map(function (x) {
        var code = (x.match(/"([a-z_]+)"/) || [])[1]; return '<div class="rule ' + (hit[code] ? 'hit' : v.decisions.length ? 'pass' : '') + '">' + esc(x.replace(/ if.*$/, '')) + ' <span class="small">' + esc(x.replace(/^.* if /, 'if ').replace(/\{\s*$/, '…')) + '</span></div>';
      }).join('') + '<p class="small">Same rule, run twice: advisory before the agent speaks, binding in the workflow before anything is written. The AI never holds the rule.</p>';
      b.innerHTML = h;
    },
    L5: function (b, v) {
      var acts = v.bpmn || [];
      b.innerHTML = '<div class="bpmn" id="bpmnc"></div><p class="small"><span class="chip sf" style="background:#dcfce7;color:#14532d">done</span><span class="chip sf">current step</span><span class="chip st">jeopardy</span> · business key <span class="mono">' + esc((v.state || {}).orderExternalId || '—') + '</span> · process <span class="mono">' + esc((v.state || {}).processInstanceId || '—') + '</span></p>' +
        (acts.length ? spanRows(acts.filter(function (a) { return a.type !== 'sequenceFlow'; }), [['Started', function (a) { return hm(T(a.start)); }], ['Step', function (a) { return esc(a.name || a.id); }], ['Type', function (a) { return '<span class="small">' + esc(a.type) + '</span>'; }], ['State', function (a) { return a.end ? '<span class="ok">done</span>' : '<b style="color:var(--l5)">current</b>'; }]]) : '<p class="small">The workflow starts when the Intent is recorded. Nothing has been written yet.</p>');
      drawBpmn($('#bpmnc', b), acts);
    },
    L6: function (b, v) {
      var calls = v.spans.filter(function (s) { return s.layer === 'L6'; });
      b.innerHTML = '<p><span class="chip sf">' + SF_CHIP + '</span><span class="chip st">' + STANDIN_CHIP + '</span> <span class="small">Click a call to see its request and response.</span></p>' +
        apiRows(calls, v, true) + (planOf(v) ? orchPanels(planOf(v)) : '') +
        '<p class="small">Everything above this layer reaches Salesforce only through TM Forum Open APIs. The L5 workflow writes the quote and the order, and only reads the installed product back (TMF637).</p>';
    },
    L7: function (b, v) {
      var n = v.network || {}, up = portIs900(v), jeo = (v.jeopardy || []).length && !up, sent = (v.milestones || []).some(function (m) { return m.name === 'SentToOSS'; });
      var orch = (v.milestones || []).some(function (m) { return (m.name === 'SentToOSS' && (m.body || {}).via) || m.name === 'FulfilmentPlan'; });
      var col = up ? '#16a34a' : jeo ? '#c2410c' : '#64748b';
      b.innerHTML = '<p><span class="lab mock">mocked, operator\'s digital core (network and edge)</span> <span class="small">network view is our illustration</span></p>' +
        '<svg class="net" viewBox="0 0 640 200" role="img" aria-label="Network view of site 4471">' +
        '<rect x="10" y="60" width="150" height="80" rx="10" fill="#eef2f7" stroke="#64748b"/><text x="85" y="92" text-anchor="middle" font-size="13" font-weight="700">' + esc((n.exchange || 'Martlesham Heath').replace(/ exchange.*$/, '')) + '</text><text x="85" y="110" text-anchor="middle" font-size="11" fill="#555">exchange</text><text x="85" y="126" text-anchor="middle" font-size="11" fill="' + (jeo ? '#c2410c' : '#555') + '">free 900 ports: ' + (up ? 'in use' : jeo ? '0' : '1') + '</text>' +
        '<line x1="160" y1="100" x2="420" y2="100" stroke="' + col + '" stroke-width="' + (up ? 7 : 3) + '" stroke-dasharray="' + (sent && !up ? '8 6' : '0') + '"/><text x="320" y="30" text-anchor="middle" font-size="11" fill="#555">fibre path: ' + esc([].concat(n.fibrePath || ['MH exchange OLT-07', 'Splitter cabinet MH-C12', 'Brightwell, 1 Fibre Way']).join(' → ')) + '</text>' +
        '<rect x="420" y="70" width="80" height="60" rx="8" fill="#fff" stroke="' + col + '" stroke-width="2"/><text x="460" y="96" text-anchor="middle" font-size="12" font-weight="700">' + (up ? '900' : '150') + ' Mbps</text><text x="460" y="113" text-anchor="middle" font-size="10" fill="#555">access port</text><text x="460" y="146" text-anchor="middle" font-size="9.5" fill="#777">' + esc((n.accessPort || {}).id || 'MH-OLT-07/1/14') + '</text>' +
        '<line x1="500" y1="100" x2="530" y2="100" stroke="#64748b" stroke-width="3"/><rect x="530" y="60" width="100" height="80" rx="10" fill="#eef4ff" stroke="#0176d3"/><text x="580" y="92" text-anchor="middle" font-size="12" font-weight="700">Site 4471</text><text x="580" y="110" text-anchor="middle" font-size="11" fill="#555">Brightwell</text><text x="580" y="125" text-anchor="middle" font-size="11" fill="#555">Martlesham</text>' +
        '<text x="320" y="180" text-anchor="middle" font-size="12" fill="' + col + '">' + (up ? (orch ? 'Bandwidth profile 150 → 900 and router swapped when the TMF641 order completed' : 'Port upgraded 150 → 900 when the legacy OSS step completed (fallback route, recorded run)') : jeo ? 'No 900 Mbps port free: the order is in jeopardy (+2 days)' : sent ? (orch ? 'TMF641 order sent by Salesforce order orchestration (network order adapter, mocked)' : 'Fallback route (recorded run): order sent to the legacy OSS, waiting for the overnight batch') : 'Today: Fibre 150 on this port') + '</text></svg>' +
        '<div class="sec">Platform (target state, mocked)</div><p>' + PLATFORM + '</p><p class="small">Provided by the operator\'s digital core, mocked in the MVP.</p>' +
        '<p class="small">The records about the network (inventory, site, OSS order) stay in L6; L7 is the network and platform itself.</p>';
    },
    L8: function (b, v) {
      var sp = v.spans.slice().sort(function (a, c) { return T(a.start_ts) - T(c.start_ts); });
      if (!sp.length) { b.innerHTML = '<p class="small">No steps yet.</p>'; return; }
      var t0 = T(sp[0].start_ts), t1 = Math.max.apply(null, sp.map(function (s) { return s.running ? nowT() : T(s.end_ts); })), W = Math.max(1, t1 - t0);
      b.innerHTML = '<p>Trace <span class="mono">' + esc(v.conversation.trace_id) + '</span> · ' + sp.length + ' steps · ' + ((t1 - t0) / 1000).toFixed(1) + ' s end to end. Built from the L3 audit log; OTel-style trace and span IDs.</p>' +
        '<div class="tl">' + sp.map(function (s) {
          var a = (T(s.start_ts) - t0) / W * 100, w = ((s.running ? nowT() : T(s.end_ts)) - T(s.start_ts)) / W * 100;
          return '<div class="tlr" style="--c:var(--' + s.layer.toLowerCase() + ')" title="span ' + esc(s.span_id) + ' parent ' + esc(s.parent_span_id || '—') + '"><span class="lyn">' + s.layer + '</span><span class="st">' + esc(s.step) + '<div class="mono small">' + esc(s.span_id) + '</div></span><span class="bar"><i style="left:' + a.toFixed(2) + '%;width:' + Math.max(0.3, w).toFixed(2) + '%"></i></span><span class="small">' + ms(s) + '</span></div>';
        }).join('') + '</div>';
    }
  };
  function drawBpmn(el, acts) {
    if (!window.BpmnJS || !BPMN_XML) { el.innerHTML = '<p class="small">BPMN viewer not loaded.</p>'; return; }
    if (!bpmnViewer) { bpmnViewer = new window.BpmnJS(); bpmnLoaded = bpmnViewer.importXML(BPMN_XML); }
    bpmnViewer.attachTo(el);
    bpmnLoaded.then(function () {
      var canvas = bpmnViewer.get('canvas'), reg = bpmnViewer.get('elementRegistry');
      reg.getAll().forEach(function (e) { ['done', 'cur', 'jeo', 'stp'].forEach(function (m) { canvas.removeMarker(e.id, m); }); });
      acts.forEach(function (a) { if (!reg.get(a.id)) return; canvas.addMarker(a.id, /Jeopardy|Delay/.test(a.id) ? 'jeo' : a.mark || (a.end ? 'done' : 'cur')); });
      canvas.zoom('fit-viewport');
    });
  }

  /* ---------- exposed APIs (architecture tab) ---------- */
  var EXPOSED = [
    { g: 'Salesforce (out of the box)', c: 'sf', rows: [
      ['TMF629', 'Customer', 'GET', '/services/data/v68.0/connect/comms/customermanagement/v4/customer/{id}', 'Customer (Account)'],
      ['TMF637', 'Product Inventory', 'GET', '/services/data/v68.0/connect/comms/productinventorymanagement/v5/productinventory/{id}', 'Installed product by id (serial number)']] },
    { g: 'TMF facade within Salesforce (Apex)', c: 'sf', rows: [
      ['TMF620', 'Product Catalog', 'GET', '/services/apexrest/agentictelco/tmf620/productOffering', 'Offers, prices, characteristics'],
      ['TMF671', 'Promotion', 'GET', '/services/apexrest/agentictelco/tmf671/promotion', 'Promotions in the org'],
      ['TMF632', 'Party', 'GET', '/services/apexrest/agentictelco/tmf632/organization/{id}', 'Organization with contacts and their roles'],
      ['TMF637', 'Product Inventory', 'GET', '/services/apexrest/agentictelco/tmf637/product?relatedParty.id=', 'Installed products of a customer, with site and contract end'],
      ['TMF637', 'Product Inventory', 'POST', '/services/apexrest/agentictelco/tmf637/product', 'Create an installed product (idempotent on serial number); not used by the MVP run'],
      ['TMF637', 'Product Inventory', 'PATCH', '/services/apexrest/agentictelco/tmf637/product/{id}', 'Status, end date, Upgrade productRelationship; not used by the MVP run'],
      ['TMF648', 'Quote', 'POST · PATCH · GET', '/services/apexrest/agentictelco/tmf648/quote', 'Quote and quote lines'],
      ['TMF622', 'Product Order', 'POST · PATCH · GET', '/services/apexrest/agentictelco/tmf622/productOrder', 'Order and order items; adds the usage record internally']] },
    { g: 'Legacy stand-ins (mocked)', c: 'st', rows: [
      ['TMF666', 'Account', 'GET', '/tmf-api/accountManagement/v4/billingAccount/{id}', 'Billing B balance'],
      ['TMF679', 'Product Offering Qualification', 'GET', '/tmf-api/productOfferingQualification/v5/availability/{addressKey}', 'What can be delivered at the site'],
      ['TMF639', 'Resource Inventory', 'GET', '/tmf-api/resourceInventoryManagement/v4/site/{id}', 'Exchange and access port'],
      ['TMF641', 'Service Order', 'POST · GET', '/tmf-api/serviceOrdering/v4/serviceOrder', 'Legacy OSS, overnight batch: fallback route, only in the recorded delayed journey (the live workflow stops if there is no fulfilment plan)'],
      ['—', 'Payment link', 'POST', '/payment/link', 'Overdue-balance payment link (not a TMF API)']] },
    { g: 'Network order adapter (Mocked), called by Salesforce order orchestration', c: 'net', rows: [
      ['TMF641', 'Service Order', 'POST · GET', '/tmf-api/serviceOrdering/v4/serviceOrder', 'The one outbound network interaction: one service order with an action code per CFS (acknowledged → inProgress → completed)']] },
    { g: 'Network side, inside the mocked network (not called by Salesforce; shown as data in the TMF641 response)', c: 'netside', rows: [
      ['TMF685', 'Resource Pool Management', '—', 'x-networkFulfilment.reservation', 'The network reserves the access port capacity and the new router'],
      ['TMF639', 'Resource Inventory', '—', 'x-networkFulfilment.resourceInventory', 'The network updates its own resources'],
      ['TMF638', 'Service Inventory', '—', 'x-networkFulfilment.serviceInventory', 'The network records its installed services']] }];
  function exposedApis() {
    return '<div class="ph boxh"><h2>' + esc(UA.apisHeading || 'Exposed APIs (TMF-aligned)') + '</h2></div><div class="panel boxb" id="exposed">' +
      EXPOSED.map(function (g) {
        return '<div class="sec">' + (g.c === 'st' ? '<span class="chip st">' + STANDIN_CHIP + '</span>' : g.c === 'net' ? '<span class="chip st">' + NET_CHIP + '</span> ' + esc(g.g) + '. ' + SIM_SENTENCE : g.c === 'netside' ? '<span class="chip st">' + NET_CHIP + '</span> ' + esc(g.g) + '.' : '<span class="chip sf">' + SF_CHIP + '</span> Provided by: ' + esc(g.g)) + '</div><table class="t api"><tr><th>TMF API</th><th>Method</th><th>Path</th><th>Used for</th></tr>' +
          g.rows.map(function (r) { return '<tr><td><span class="tmf"><b>' + r[0] + '</b> ' + esc(r[1]) + '</span></td><td><span class="mth">' + esc(r[2]) + '</span></td><td class="mono small">' + esc(r[3]) + '</td><td>' + esc(r[4]) + '</td></tr>'; }).join('') + '</table>';
      }).join('') + '<p class="small">TMF-aligned resource shapes. The facade classes (AgenticTelco_TMF6nn) only map data; the rules live in the policy and the workflow.</p></div>';
  }

  /* ---------- live mode ---------- */
  var poll = null;
  function api(path, body) { return fetch(path, body ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : {}).then(function (r) { if (!r.ok) throw new Error(path + ' ' + r.status); return r.json(); }); }
  function refresh() { if (!S.cid) return Promise.resolve(); return api('/api/state?conversationId=' + encodeURIComponent(S.cid)).then(function (s) { S.full = s; render(); }).catch(function () { }); }
  function startCase(id) {
    closeLayer(); S.step = null; archKey = '';
    if (!LIVE) return loadRecording(id);
    if (S.busy) return;
    S.busy = true; S.caseId = id; S.full = null; S.cid = null; render();
    api('/api/demo/start', { case: id }).then(function (r) { S.cid = r.conversationId; S.busy = false; if (!poll) poll = setInterval(refresh, 1000); return refresh(); })
      .catch(function (e) { S.busy = false; alert('Could not start: ' + e.message); render(); });
  }
  function send(text) {
    text = (text || '').trim(); if (!text || !S.cid || S.busy) return;
    if ($('#msg')) $('#msg').value = '';
    S.busy = true; render();
    api('/api/chat', { conversationId: S.cid, message: text }).then(function () { S.busy = false; return refresh(); }).catch(function (e) { S.busy = false; render(); alert('Chat failed: ' + e.message); });
  }

  /* ---------- recorded mode ---------- */
  function buildTimeline(full) {
    var ts = [];
    var push = function (x) { var t = T(x); if (!isNaN(t)) ts.push(t); };
    (full.messages || []).forEach(function (m) { push(m.at); });
    (full.spans || []).forEach(function (s) { push(s.start_ts); push(s.end_ts); });
    (full.decisions || []).forEach(function (d) { push(d.at); }); (full.consent || []).forEach(function (d) { push(d.at); });
    (full.milestones || []).forEach(function (d) { push(d.at); }); (full.jeopardy || []).forEach(function (d) { push(d.at); });
    (full.reports || []).forEach(function (d) { push(d.creationDate); }); (full.bpmn || []).forEach(function (a) { push(a.start); push(a.end); });
    ts = ts.sort(function (a, b) { return a - b; }).filter(function (t, i, a) { return i === 0 || t !== a[i - 1]; });
    var GAP = 1600, r = [0];
    for (var i = 1; i < ts.length; i++) r.push(r[i - 1] + Math.min(ts[i] - ts[i - 1], GAP));
    var start = ts[0] - 1000, total = r[r.length - 1] + 1000;
    return {
      tStart: start, tEnd: ts[ts.length - 1], total: total,
      timeAt: function (frac) { var R = frac * total - 1000; if (R < 0) return ts[0] + R; for (var i = 1; i < r.length; i++) if (r[i] >= R) { var f = (R - r[i - 1]) / Math.max(1, r[i] - r[i - 1]); return ts[i - 1] + f * (ts[i] - ts[i - 1]); } return ts[ts.length - 1]; },
      fracAt: function (t) { if (t <= ts[0]) return Math.max(0, (t - start) / total); for (var i = 1; i < ts.length; i++) if (ts[i] >= t) { var f = (t - ts[i - 1]) / Math.max(1, ts[i] - ts[i - 1]); return (1000 + r[i - 1] + f * (r[i] - r[i - 1])) / total; } return 1; }
    };
  }
  function loadRecording(id) {
    stopPlay();
    var rec = REC[id]; S.caseId = id;
    if (!rec) { S.full = null; S.rec = null; modebar(); render(); return; }
    S.full = rec.state; var tl = buildTimeline(rec.state);
    S.rec = Object.assign({ title: rec.title, recordedAt: rec.recordedAt }, tl); S.t = tl.tStart; modebar(); render(); startPlay();
  }
  function startPlay() { if (!S.rec) return; stopPlay(); var last = performance.now(); S.play = setInterval(function () { var n = performance.now(), dt = (n - last) * S.speed; last = n; var f = S.rec.fracAt(S.t) + dt / S.rec.total; if (f >= 1) { S.t = S.rec.tEnd; stopPlay(); } else S.t = S.rec.timeAt(f); render(); }, 120); var b = $('#b-play'); if (b) b.textContent = 'Pause'; }
  function stopPlay() { if (S.play) clearInterval(S.play); S.play = null; var b = $('#b-play'); if (b) b.textContent = 'Play'; }
  function togglePlay() { if (S.play) stopPlay(); else { S.step = null; if (S.rec && S.t >= S.rec.tEnd) S.t = S.rec.tStart; startPlay(); } }

  window.__mvp = { S: S, view: view, windows: windows, openLayer: openLayer, setTab: setTab, selectStep: selectStep, startCase: startCase, render: render };
  shell();
  if (LIVE) setInterval(function () { if (S.cid) render(); }, 500);
})();
