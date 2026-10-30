/* AgenticTelco MVP UI. Business view (left) and the eight Zero Gravity layers (right).
   Live mode polls the gateway (/api/state); recorded mode replays a recorded run (final /api/state, filtered by time). */
(function () {
  'use strict';
  var CFG = window.MVP_CFG || {}, COPY = CFG.copy, BPMN_XML = CFG.bpmn, REGO = CFG.rego || '';
  var LIVE = CFG.mode === 'live', REC = CFG.recordings || {};
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var T = function (x) { return x ? Date.parse(String(x).replace(/([+-]\d\d)(\d\d)$/, '$1:$2')) : NaN; };
  var hm = function (ms) { var d = new Date(ms); return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Europe/London' }); };
  var LAYER_IDS = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7', 'L8'];
  var CASES = [
    { id: 'happy', t: 'Happy path', s: 'Sam (Decision Maker) upgrades' },
    { id: 'notauth', t: 'Not authorised', s: 'Alex (Business User) asks' },
    { id: 'overdue', t: 'Overdue balance', s: 'Policy says no' },
    { id: 'delayed', t: 'Order delayed', s: '+2 days, Sam told first' }];
  var OPENING = "We're taking on 15 more staff at the Martlesham office next month, 35 people in total, and moving everyone to cloud video calls. Our broadband already struggles. What do you suggest?";
  var HOSTING = 'The agent and model run locally in our stack. Salesforce runs on instance GBR58 (REPORTED; UK region to be confirmed).';
  var PLATFORM = 'Kubernetes · secrets vault · network zones · API gateway · agent and workload identity · event bus · UK hosting';
  var S = { tab: 'demo', caseId: null, cid: null, full: null, t: Infinity, busy: false, open: null, presenter: false, follow: false, play: null, speed: 1, rec: null };
  var layerCopy = {}; (COPY.layers || []).forEach(function (l) { layerCopy[l.id] = l; });

  function statusKind(s) { s = (s || '').toLowerCase(); if (/^mock/.test(s)) return ['mock', 'Mocked']; if (/mock|stand-in/.test(s)) return ['mix', 'Real + stand-ins']; return ['real', 'Real']; }

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

  /* ---------- derived business facts ---------- */
  function facts(v) {
    var st = (v && v.state) || {}, pack = st.contextPack || {}, f = {};
    f.who = st.contactFullName ? st.contactFullName + ' · ' + st.contactRole : '—';
    f.current = (pack.currentBroadband && ((pack.currentBroadband.product || pack.currentBroadband.name) + ' · £' + pack.currentBroadband.monthlyPriceGBP + '/month')) || 'AgenticTelco Fibre 150 · £27/month';
    var ce = (pack.contractMonthsLeft || {}).contractEnd; f.contractEnd = ce ? new Date(ce + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '28 August 2027';
    f.site = (pack.site && pack.site.name) || 'Site 4471, Martlesham';
    return f;
  }
  function stage(v) {
    var c = S.caseId, out = [];
    var msgs = v ? v.messages : [], users = msgs.filter(function (m) { return m.role === 'user'; }), asst = msgs.filter(function (m) { return m.role === 'assistant'; });
    var adv = v && v.decisions.filter(function (d) { return d.mode === 'advisory'; }), anyAllow = adv && adv.some(function (d) { return d.result.allow; });
    var denyAll = adv && adv.length && !anyAllow;
    var checked = v && v.spans.some(function (s) { return s.layer === 'L4'; });
    var consent = v && v.consent.length, jeo = v && v.jeopardy && v.jeopardy.length, live = v && v.intent && v.intent.lifecycle_status === 'fulfilled';
    var denyReason = denyAll ? (adv[0].result.deny || [])[0] : null;
    var rec = (v && v.state && v.state.recommended) || null;
    out.push({ b: 'Sam asks', s: c === 'notauth' ? 'Alex asks' : 'needs more speed', k: users.length ? 'done' : '' });
    out.push({ b: 'Checks', s: 'customer, site, contract, policy', k: checked ? 'done' : (users.length ? 'now' : '') });
    if (denyAll) out.push({ b: 'Recommends', s: denyReason === 'not_authorised' ? 'Not authorised: ask Sam' : denyReason === 'overdue_balance' ? 'Blocked: overdue balance' : 'Not allowed', k: asst.length ? 'blocked' : 'now' });
    else out.push({ b: 'Recommends', s: 'Fibre 900 £45/month', k: asst.length ? 'done' : (checked ? 'now' : '') });
    out.push({ b: 'Agrees', s: denyAll ? 'nothing to agree' : 'Sam says yes', k: denyAll ? 'skip' : consent ? 'done' : '' });
    out.push({ b: 'Delay', s: c === 'delayed' || jeo ? '+2 days, Sam told first' : 'no delay in this case', k: jeo ? 'delay' : (c === 'delayed' ? '' : 'skip') });
    out.push({ b: 'Live', s: live ? 'Fibre 900 live' : denyAll ? 'no order' : 'Fibre 900 live', k: live ? 'live' : denyAll ? 'skip' : (consent ? 'now' : '') });
    for (var i = out.length - 1; i >= 0; i--) if (out[i].k === 'now') { for (var j = i - 1; j >= 0; j--) if (out[j].k === 'now') out[j].k = 'done'; break; }
    return out;
  }

  /* ---------- rendering ---------- */
  function shell() {
    document.title = 'AgenticTelco MVP · Agent upgrades a Business Customer Service (B2B)';
    $('#app').innerHTML =
      '<header class="hd"><div class="brand">' + (CFG.mark || '') + '<div><div class="brand-name">AgenticTelco</div><div class="brand-sub">TelForce business portal</div></div></div>' +
      '<div class="ttl"><div class="kick">AGENTICTELCO MVP · BASED ON ZERO GRAVITY ARCHITECTURE</div><h1>Agent upgrades a Business Customer Service (B2B), on existing systems</h1></div>' +
      '<div class="tabs"><button data-tab="demo" class="on">Demo</button><button data-tab="arch">Architecture</button></div>' +
      '<button class="tb" id="b-pres" title="Presenter mode (P)">Presenter</button>' + (LIVE ? '' : '<button class="tb" id="btn-lock" title="Lock">Lock</button>') + '</header>' +
      '<div class="modebar' + (LIVE ? '' : ' rec') + '" id="modebar"></div>' +
      '<div class="banner"><div class="big">Agent proposes<i>·</i>Policy decides<i>·</i>Workflow writes</div><div class="small">The AI never holds business rules and never writes to a system of record</div></div>' +
      '<section id="v-demo"><div class="wrap"><div class="col-l"></div><div class="col-r"></div></div></section>' +
      '<section id="v-arch" hidden></section>' +
      '<div class="dr" id="drawer" aria-hidden="true"></div>' +
      '<div class="foot">Concept demo by Lalit Chauhan · not an official Salesforce product · ' + esc(HOSTING) + '</div>';
    $('.col-l').innerHTML =
      '<div class="panel"><div class="ph"><h2>Business view</h2><span class="sub">Brightwell Design Ltd · Fibre 150 → Fibre 900</span></div>' +
      '<div class="cases">' + CASES.map(function (c, i) { return '<button class="case" data-case="' + c.id + '"><b>' + (i + 1) + '. ' + c.t + '</b><span>' + c.s + '</span></button>'; }).join('') + '</div>' +
      '<div class="chev" id="chev"></div>' +
      '<div class="portal"><div class="av" id="av">S</div><div class="who" id="who">AgenticTelco Business portal · choose a case to start</div><span class="badge" id="ist">no intent yet</span></div>' +
      '<div class="chat" id="chat"></div>' +
      (LIVE ? '<div class="quick" id="quick"></div><div class="composer"><textarea id="msg" placeholder="Type as the customer…"></textarea><button class="btn" id="send">Send</button></div>' : '') +
      '<div class="facts" id="facts"></div>' +
      '<div class="keys"><div class="key"><b>Salesforce is the system of record only</b>it keeps the records; the agent never writes to it</div><div class="key"><b>Rules live in one versioned policy</b>OPA (Rego) · checked advisory, then binding</div>' +
      '<div class="key"><b>Open TM Forum APIs</b>TMF921 · 629 · 632 · 637 · 620 · 648 · 622 · 671</div><div class="key"><b>Every decision is traceable</b>one trace ID from chat to Salesforce record</div></div></div>';
    $('.col-r').innerHTML =
      '<div class="panel"><div class="ph"><h2>Architecture view · Zero Gravity layers</h2><span class="sub">lights up live · click a layer</span></div><div class="layers" id="layers">' +
      LAYER_IDS.map(function (id) {
        var l = layerCopy[id] || {}, k = statusKind(l.status);
        return '<div class="ly" data-layer="' + id + '" style="--c:var(--' + id.toLowerCase() + ')"><div class="n">' + id + '</div><div><div class="nm">' + esc(l.name) + '<small>' + esc(l.chip && l.chip !== l.name ? l.chip : '') + '</small></div><div class="q">' + esc(l.question) + '</div><div class="now"></div></div>' +
          '<div class="rt"><span class="lab ' + k[0] + '" title="' + esc(l.status) + '">' + k[1] + '</span><span class="cnt"></span></div></div>';
      }).join('') + '</div></div>';
    document.querySelectorAll('.tabs button').forEach(function (b) { b.onclick = function () { setTab(b.dataset.tab); }; });
    document.querySelectorAll('.case').forEach(function (b) { b.onclick = function () { startCase(b.dataset.case); }; });
    document.querySelectorAll('.ly').forEach(function (b) { b.onclick = function () { openLayer(b.dataset.layer); }; });
    $('#b-pres').onclick = togglePresenter;
    if (LIVE) { $('#send').onclick = function () { send($('#msg').value); }; $('#msg').onkeydown = function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send($('#msg').value); } }; }
    document.addEventListener('keydown', function (e) {
      if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
      if (e.key === 'Escape') closeLayer(); else if (e.key === 'p' || e.key === 'P') togglePresenter();
      else if (/^[1-4]$/.test(e.key)) startCase(CASES[+e.key - 1].id); else if (e.key === ' ' && !LIVE) { e.preventDefault(); togglePlay(); }
    });
    renderArch(); modebar(); render();
  }
  function setTab(t) { S.tab = t; document.querySelectorAll('.tabs button').forEach(function (b) { b.classList.toggle('on', b.dataset.tab === t); }); $('#v-demo').hidden = t !== 'demo'; $('#v-arch').hidden = t !== 'arch'; }
  function togglePresenter() { S.presenter = !S.presenter; S.follow = S.presenter; document.body.classList.toggle('presenter', S.presenter); $('#b-pres').classList.toggle('on', S.presenter); }

  function modebar() {
    var m = $('#modebar');
    if (LIVE) { m.innerHTML = '<span class="badge">LIVE</span><span>Live run against the real Salesforce org, local model ' + esc(CFG.model || 'Qwen3-4B-Instruct-2507') + ', Operaton and OPA. Legacy systems are labelled stand-ins.</span><span class="sp"></span><span id="mstat"></span>'; return; }
    var r = S.rec;
    m.innerHTML = '<span class="badge">RECORDED RUN</span><span>' + (r ? 'Recorded run of “' + esc(r.title) + '” on ' + esc(new Date(r.recordedAt).toLocaleString('en-GB', { timeZone: 'Europe/London', dateStyle: 'medium', timeStyle: 'short' })) + ' (UK time), replayed from the real data it produced. Long waits are shortened.' : 'Recorded runs: choose a case to replay what really happened.') + '</span><span class="sp"></span>' +
      '<span class="ctrl"><button class="tb" id="b-play">' + (S.play ? 'Pause' : 'Play') + '</button><input type="range" id="scrub" min="0" max="1000" value="0"><button class="tb" id="b-end">Skip to end</button>' +
      '<select id="spd" class="tb"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></span>';
    $('#b-play').onclick = togglePlay; $('#b-end').onclick = function () { if (S.rec) { stopPlay(); S.t = S.rec.tEnd; render(); } };
    $('#spd').value = String(S.speed); $('#spd').onchange = function () { S.speed = +this.value; };
    $('#scrub').oninput = function () { if (!S.rec) return; stopPlay(); S.t = S.rec.timeAt(+this.value / 1000); render(); };
  }

  function render() {
    var v = view(S.full, S.t), cid = S.caseId;
    document.querySelectorAll('.case').forEach(function (b) { b.classList.toggle('on', b.dataset.case === cid); b.disabled = S.busy && LIVE; });
    $('#chev').innerHTML = stage(v).map(function (c) { return '<div class="cv ' + c.k + '"><b>' + c.b + '</b>' + esc(c.s) + '</div>'; }).join('');
    var st = (v && v.state) || {};
    $('#av').textContent = (st.contactName || 'S')[0];
    $('#who').textContent = st.contactFullName ? 'AgenticTelco Business portal · signed in as ' + st.contactFullName + ' (' + st.contactRole + ') · Brightwell Design Ltd' : 'AgenticTelco Business portal · choose a case to start';
    var is = v && v.intent ? v.intent.lifecycle_status : null;
    $('#ist').textContent = is ? 'Intent ' + is : 'no intent yet'; $('#ist').style.color = is === 'fulfilled' ? 'var(--ok)' : is === 'atRisk' ? '#fdba74' : '#fff';
    renderChat(v);
    var f = facts(v);
    $('#facts').innerHTML = '<div>Customer<b>Brightwell Design Ltd</b></div><div>Contact<b>' + esc(f.who) + '</b></div><div>' + (is === 'fulfilled' ? 'Now' : 'Today') + '<b>' + esc(is === 'fulfilled' ? 'AgenticTelco Fibre 900 · £45/month (live)' : f.current) + '</b></div><div>Contract end<b>' + esc(f.contractEnd) + ' (kept)</b></div>';
    var hl = hotLayers(v);
    LAYER_IDS.forEach(function (id) {
      var el = $('.ly[data-layer="' + id + '"]'), h = hl.hot[id];
      el.classList.toggle('hot', !!h); el.classList.toggle('touched', !!hl.used[id]);
      $('.now', el).textContent = h ? '▶ ' + (h.step || '') + (h.runtime ? ' · ' + h.runtime : '') : (hl.used[id] ? lastStep(v, id) : '');
      $('.cnt', el).textContent = hl.used[id] ? hl.used[id] + (id === 'L7' ? ' event' : ' step') + (hl.used[id] > 1 ? 's' : '') : '';
    });
    if (S.follow) { var hk = Object.keys(hl.hot).filter(function (k) { return k !== 'L8'; }).pop(); if (hk && hk !== S.open) openLayer(hk, true); }
    if (S.open) renderLayer(S.open, v);
    if (!LIVE && S.rec && $('#scrub')) { $('#scrub').value = Math.round(S.rec.fracAt(S.t) * 1000); }
    if (LIVE && $('#mstat')) $('#mstat').textContent = S.busy ? 'agent working…' : (S.cid ? 'conversation ' + S.cid : '');
  }
  function lastStep(v, id) { var s = v.spans.filter(function (x) { return x.layer === id; }).pop(); if (id === 'L7') return 'Port ' + (portIs900(v) ? '900' : '150') + ' Mbps at site 4471'; return s ? s.step : ''; }
  function linkify(t) { return esc(t).replace(/(https:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>'); }
  function renderChat(v) {
    var c = $('#chat'), msgs = v ? v.messages : [];
    var html = msgs.map(function (m) {
      var pro = m.meta && m.meta.proactive, ok = pro && /Complies/.test(m.meta.reportState || '');
      return '<div class="msg ' + m.role + (pro ? ' pro' + (ok ? ' ok' : '') : '') + '">' + linkify(m.content) + '<span class="meta">' + (m.role === 'user' ? esc((v.state || {}).contactName || 'Customer') : 'AgenticTelco agent' + (pro ? ' · proactive update' : '')) + ' · ' + hm(T(m.at)) + '</span></div>';
    }).join('');
    var lastUser = msgs.length && msgs[msgs.length - 1].role === 'user';
    if ((LIVE && S.busy) || (!LIVE && lastUser)) html += '<div class="typing">Agent is checking…</div>';
    if (!msgs.length) html = '<div class="empty">' + (S.caseId ? (LIVE ? 'Press Send to ask the opening question as the customer.' : 'Press Play to replay the recorded run.') : 'Choose one of the four cases above. Each starts from Brightwell on Fibre 150 at £27 a month, contract to 28 August 2027.') + '</div>';
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
    $('.db', d).scrollTop = keepScroll;
  }
  function spanRows(list, cols) { return '<table class="t"><tr>' + cols.map(function (c) { return '<th>' + c[0] + '</th>'; }).join('') + '</tr>' + list.map(function (s) { return '<tr>' + cols.map(function (c) { return '<td>' + c[1](s) + '</td>'; }).join('') + '</tr>'; }).join('') + '</table>'; }
  function ms(s) { return s.running ? '<span class="warn">running…</span>' : (s.duration_ms >= 1000 ? (s.duration_ms / 1000).toFixed(1) + ' s' : Math.round(s.duration_ms) + ' ms'); }
  function rtChip(s) { var r = s.runtime || ''; if (/facade/i.test(r)) return '<span class="chip fac">TMF facade inside Salesforce (Apex)</span>'; if (/native Salesforce/i.test(r)) return '<span class="chip sf">native Salesforce API</span>'; if (/stand-in/i.test(r)) return '<span class="chip st">legacy stand-in (mocked)</span>'; return '<span class="chip ours">' + esc(r) + '</span>'; }
  function linkFor(s, v) {
    var L = v.links || {}, ms_ = v.milestones || [], has = function (n) { return ms_.some(function (m) { return m.name === n; }); }, a = function (u, t) { return u ? '<a class="link" target="_blank" rel="noopener" href="' + esc(u) + '">' + t + '</a>' : ''; };
    if (/Create quote/.test(s.step) && has('QuoteCreated')) return a(L.quote, 'Quote');
    if (/Place upgrade order|Order in progress|Complete order/.test(s.step) && has('OrderInProgress')) return a(L.order, 'Order ' + (L.orderNumber || ''));
    if (/Create Fibre 900/.test(s.step) && has('AssetChanged')) return a(L.newAsset, 'New asset');
    if (/Obsolete/.test(s.step)) return a(L.oldAsset, 'Fibre 150 asset');
    if (/AssetRelationship/.test(s.step) && has('AssetChanged')) return a(L.relationship, 'Upgrade link');
    if (/^Customer$/.test(s.step)) return a(L.account, 'Account');
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
      h += '<div class="sec">Consent</div>' + (v.consent.length ? v.consent.map(function (c) { return '<p>“' + esc(c.text) + '” · ' + hm(T(c.at)) + '</p>'; }).join('') : '<p class="small">No consent recorded.</p>');
      b.innerHTML = h;
    },
    L2: function (b, v) {
      var calls = v.spans.filter(function (s) { return s.layer === 'L2'; }), model = calls.filter(function (s) { return /Model call/.test(s.step); });
      var tin = 0, tout = 0; model.forEach(function (s) { tin += (s.attributes || {}).promptTokens || 0; tout += (s.attributes || {}).outputTokens || 0; });
      b.innerHTML = '<p>Model: <b>' + esc(v.model || CFG.model || '') + '</b> · ' + model.length + ' model calls · ' + tin + ' prompt tokens · ' + tout + ' output tokens (measured this run).</p>' +
        '<p class="small">The agent only proposes. It reads the context pack through MCP tools and records an Intent; it has no tool that writes to Salesforce.</p>' +
        spanRows(calls, [['Step', function (s) { return esc(s.step); }], ['Tools', function (s) { var a = s.attributes || {}; return esc((a.toolCalls || []).join(', ')); }], ['Runtime', function (s) { return '<span class="small">' + esc(s.runtime) + '</span>'; }], ['Time', ms]]);
    },
    L3: function (b, v) {
      b.innerHTML = '<div class="sec">Cross-reference: the same customer in each system</div>' +
        spanRows(v.xref || [], [['System', function (x) { return '<b>' + esc(x.system) + '</b>'; }], ['ID', function (x) { return '<span class="mono">' + esc(x.external_id) + '</span>'; }], ['Source', function (x) { return '<span class="small">' + esc(x.source) + '</span>'; }], ['Verified', function (x) { return x.verified ? '<span class="ok">✔</span>' : '✖'; }]]) +
        '<div class="sec">What we remember for this conversation</div><p>' + v.messages.length + ' messages · ' + v.decisions.length + ' policy decisions · ' + v.consent.length + ' consent · ' + v.spans.length + ' audit rows (trace <span class="mono">' + esc(v.conversation.trace_id) + '</span>)</p>' +
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
          if (k === 'sizing') val = x.staffOnVideoCalls + ' people × ' + x.mbpsPerPerson + ' Mbps = ' + x.neededMbps + ' Mbps → ' + x.bestFitName;
          if (Array.isArray(val)) val = val.map(function (y) { return typeof y === 'object' ? (y.name || JSON.stringify(y)) : y; }).join(', ');
          if (typeof val === 'object') val = JSON.stringify(val);
          if (typeof val === 'boolean') val = val ? 'yes' : 'no';
          var src = x.src || x.source || '';
          var ch = /salesforce/i.test(src) ? (/TMF6(20|48|22|71)/.test(src) ? 'fac' : 'sf') : /stand-in|billing|availab|legacy/i.test(src) ? 'st' : /L3|identity/i.test(src) ? 'l3' : 'ours';
          items.push('<div class="pk"><b>' + esc(k) + '</b>' + esc(val) + (src ? '<div><span class="chip ' + ch + '">' + esc(src) + '</span></div>' : '') + '</div>');
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
      b.innerHTML = '<p><span class="chip sf">native Salesforce API</span><span class="chip fac">TMF facade inside Salesforce (Apex)</span><span class="chip st">legacy stand-in (mocked)</span></p>' +
        spanRows(calls, [['Time', function (s) { return hm(T(s.start_ts)); }], ['Call', function (s) { return esc(s.step) + '<div class="small">' + esc(s.component) + '</div>'; }], ['API', function (s) { return '<span class="mono">' + esc(s.api) + '</span>'; }], ['Runs as', rtChip], ['Status', function (s) { return s.running ? '…' : esc(s.status); }], ['Record', function (s) { return linkFor(s, v); }]]) +
        '<p class="small">Only the L5 workflow writes (quote, order, asset change). Custom Assetize Order flow is left as is; the run checks it created no Asset.</p>';
    },
    L7: function (b, v) {
      var n = v.network || {}, up = portIs900(v), jeo = (v.jeopardy || []).length && !up, sent = (v.milestones || []).some(function (m) { return m.name === 'SentToOSS'; });
      var col = up ? '#16a34a' : jeo ? '#c2410c' : '#64748b';
      b.innerHTML = '<p><span class="lab mock">mocked, operator\'s digital core (network and edge)</span> <span class="small">network view is our illustration</span></p>' +
        '<svg class="net" viewBox="0 0 640 200" role="img" aria-label="Network view of site 4471">' +
        '<rect x="10" y="60" width="150" height="80" rx="10" fill="#eef2f7" stroke="#64748b"/><text x="85" y="92" text-anchor="middle" font-size="13" font-weight="700">' + esc((n.exchange || 'Martlesham Heath').replace(/ exchange.*$/, '')) + '</text><text x="85" y="110" text-anchor="middle" font-size="11" fill="#555">exchange</text><text x="85" y="126" text-anchor="middle" font-size="11" fill="' + (jeo ? '#c2410c' : '#555') + '">free 900 ports: ' + (up ? 'in use' : jeo ? '0' : '1') + '</text>' +
        '<line x1="160" y1="100" x2="420" y2="100" stroke="' + col + '" stroke-width="' + (up ? 7 : 3) + '" stroke-dasharray="' + (sent && !up ? '8 6' : '0') + '"/><text x="320" y="30" text-anchor="middle" font-size="11" fill="#555">fibre path: ' + esc([].concat(n.fibrePath || ['MH exchange OLT-07', 'Splitter cabinet MH-C12', 'Brightwell, 1 Fibre Way']).join(' → ')) + '</text>' +
        '<rect x="420" y="70" width="80" height="60" rx="8" fill="#fff" stroke="' + col + '" stroke-width="2"/><text x="460" y="96" text-anchor="middle" font-size="12" font-weight="700">' + (up ? '900' : '150') + ' Mbps</text><text x="460" y="113" text-anchor="middle" font-size="10" fill="#555">access port</text><text x="460" y="146" text-anchor="middle" font-size="9.5" fill="#777">' + esc((n.accessPort || {}).id || 'MH-OLT-07/1/14') + '</text>' +
        '<line x1="500" y1="100" x2="530" y2="100" stroke="#64748b" stroke-width="3"/><rect x="530" y="60" width="100" height="80" rx="10" fill="#eef4ff" stroke="#0176d3"/><text x="580" y="92" text-anchor="middle" font-size="12" font-weight="700">Site 4471</text><text x="580" y="110" text-anchor="middle" font-size="11" fill="#555">Brightwell</text><text x="580" y="125" text-anchor="middle" font-size="11" fill="#555">Martlesham</text>' +
        '<text x="320" y="180" text-anchor="middle" font-size="12" fill="' + col + '">' + (up ? 'Port upgraded 150 → 900 when the OSS step completed' : jeo ? 'No 900 Mbps port free: the order is in jeopardy (+2 days)' : sent ? 'Order sent to the legacy OSS, waiting for the overnight batch' : 'Today: Fibre 150 on this port') + '</text></svg>' +
        '<div class="sec">Platform (target state, mocked)</div><p>' + PLATFORM + '</p><p class="small">Provided by the operator\'s digital core, mocked in the MVP. MVP runs on a single host (native processes in this build; Docker Compose in the design). ' + esc(HOSTING) + '</p>' +
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
      reg.getAll().forEach(function (e) { ['done', 'cur', 'jeo'].forEach(function (m) { canvas.removeMarker(e.id, m); }); });
      acts.forEach(function (a) { if (!reg.get(a.id)) return; canvas.addMarker(a.id, /Jeopardy|Delay/.test(a.id) ? 'jeo' : a.end ? 'done' : 'cur'); });
      canvas.zoom('fit-viewport');
    });
  }

  /* ---------- architecture tab ---------- */
  function renderArch() {
    var g = COPY.glossary || [];
    $('#v-arch').innerHTML = '<div class="arch"><h2 style="margin:4px 0">How the new architecture works</h2>' +
      '<div class="flow"><span><b>Sam</b> asks in chat</span><em>→</em><span>L1 Intent</span><em>→</em><span>L2 Agent proposes</span><em>→</em><span>L4 Context &amp; Policy decides</span><em>→</em><span>L5 Workflow writes</span><em>→</em><span>L6 Salesforce + legacy</span><em>→</em><span>L7 network</span><em>·</em><span>L3 remembers · L8 proves</span></div>' +
      '<div class="agrid">' + LAYER_IDS.map(function (id) { var l = layerCopy[id] || {}, k = statusKind(l.status); return '<div class="ac" data-layer="' + id + '" style="--c:var(--' + id.toLowerCase() + ')"><span class="lab ' + k[0] + '">' + esc(l.status) + '</span><h3>' + id + ' · ' + esc(l.name) + '</h3><div class="q">' + esc(l.question) + '</div><div class="tech">' + esc(l.label) + '</div></div>'; }).join('') + '</div>' +
      '<div class="keys" style="padding:12px 0"><div class="key"><b>Agent proposes</b>The model suggests and explains; it has no write tool and holds no rule.</div><div class="key"><b>Policy decides</b>One versioned OPA policy, checked advisory (L4) and binding (L5).</div><div class="key"><b>Workflow writes</b>BPMN (Operaton) is the only writer, through Salesforce APIs and the TMF facade layer within Salesforce.</div><div class="key"><b>Hosting</b>' + esc(HOSTING) + '</div></div>' +
      '<div class="ph" style="border:1px solid var(--line);border-radius:10px 10px 0 0"><h2>Glossary (' + g.length + ' terms, from docs/mvp/layer-panels.md)</h2><input class="glf" id="glf" placeholder="Filter terms…"></div>' +
      '<div class="panel" style="border-top:0;border-radius:0 0 10px 10px;padding:12px"><div class="gl" id="gl"></div></div></div>';
    var draw = function (f) { $('#gl').innerHTML = g.filter(function (x) { return !f || (x.term + x.definition).toLowerCase().indexOf(f) >= 0; }).map(function (x) { return '<div class="gt"><b>' + esc(x.term) + '</b> · ' + esc(x.definition) + '</div>'; }).join(''); };
    draw(''); $('#glf').oninput = function () { draw(this.value.toLowerCase()); };
    document.querySelectorAll('.ac').forEach(function (a) { a.onclick = function () { setTab('demo'); openLayer(a.dataset.layer); }; });
  }

  /* ---------- live mode ---------- */
  var poll = null;
  function api(path, body) { return fetch(path, body ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : {}).then(function (r) { if (!r.ok) throw new Error(path + ' ' + r.status); return r.json(); }); }
  function refresh() { if (!S.cid) return Promise.resolve(); return api('/api/state?conversationId=' + encodeURIComponent(S.cid)).then(function (s) { S.full = s; render(); }).catch(function () { }); }
  function startCase(id) {
    closeLayer();
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
  function togglePlay() { if (S.play) stopPlay(); else { if (S.rec && S.t >= S.rec.tEnd) S.t = S.rec.tStart; startPlay(); } }

  window.__mvp = { S: S, view: view, openLayer: openLayer, setTab: setTab, startCase: startCase, render: render };
  shell();
  if (LIVE) setInterval(function () { if (S.cid) render(); }, 500);
})();
