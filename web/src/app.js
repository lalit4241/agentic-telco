/* AgenticTelco replay UI. Everything shown comes from DATA, a recording of a real run of the open-source stack. */
(function () {
  var D = window.ZG_DATA, $ = function (s, r) { return (r || document).querySelector(s); }, $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var fmtDate = function (iso) { var d = new Date(iso); return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/London' }) + ', ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' }) + ' UK time'; };
  var OUT = { 'completed': ['ok', 'Completed'], 'blocked-by-policy': ['warn', 'Policy blocked (L4)'], 'blocked-by-policy-in-L5': ['warn', 'Policy blocked (L5 BPMN)'],
    'compensated': ['err', 'Compensated'], 'resolved': ['ok', 'Resolved'], 'not-qualified': ['neutral', 'Not qualified'] };
  var badge = function (o) { var x = OUT[o] || ['neutral', o]; return '<span class="pill ' + x[0] + '">' + esc(x[1]) + '</span>'; };
  var ownerTag = function (c) {
    if (c.owner === 'salesforce') {
      var rt = c.runtime || 'stand-in';
      if (rt === 'OOTB') return '<span class="tag sf" title="Native Communications Cloud API or standard sObject REST on the real org">Salesforce · OOTB</span>';
      if (rt === 'custom TMF API on Salesforce') return '<span class="tag sf custom" title="AgenticTelco_ Apex REST on the real org, TMF shapes">custom TMF API on Salesforce</span>';
      if (/^our layer/.test(rt)) return '<span class="tag ours" title="' + esc(rt) + '">our layer (native TMF679 tried)</span>';
      return '<span class="tag standin" title="Salesforce contract served by the stand-in">' + esc(rt) + '</span>';
    }
    if (c.owner === 'oss') return '<span class="tag oss">OSS (mocked)</span>';
    return '<span class="tag ours">our layer</span>';
  };
  var sor = D.stack.sor || {};
  var sorText = D.stack.sorMode === 'commscloud' ? 'real Comms Cloud org ' + esc(sor.orgAlias || '') + ' (API ' + esc(sor.apiVersion || '') + ') · ' + esc(sor.salesforceRestCalls || 0) + ' Salesforce REST calls' : 'TMF stand-in (real org not connected)';

  document.getElementById('replay-bar').innerHTML = '<b>Replay</b> · ' + esc(D.label) + ' (' + esc(fmtDate(D.recordedAt)) + ') · L5 engine: <b>' + esc(D.stack.l5Engine) +
    '</b> · events: ' + esc(D.stack.eventBus) + ' · models: ' + esc(D.stack.inference) + ' · inference stub calls: <b>' + D.stack.inferenceStubCalls +
    '</b> · Salesforce: <b>' + sorText + '</b>';

  var LAYERS = [
    ['L1', 'Intent & Experience', 'This UI + TMF921 intent API + read-only GraphQL (Strawberry)', 'ours'],
    ['L2', 'Agent Mesh', 'LangGraph care agent, MCP tools, A2A network agent', 'ours'],
    ['L3', 'Data Foundations', 'PostgreSQL + pgvector, Kafka TMF688 events', 'ours'],
    ['L4', 'Enterprise Context', 'OPA policy: credit, consent, network, AI guardrails, model allow-list', 'ours'],
    ['L5', 'Deterministic Execution', 'Operaton BPMN saga: OPA-gated writes, compensation, idempotent workers', 'ours'],
    ['L6', 'Agent-Ready SoRs', 'Salesforce Comms Cloud org: OOTB TMF APIs first (629, 632, 637), custom TMF APIs in Apex where the org has none (620, 648, 622); OSS mocked', 'salesforce'],
    ['L7', 'Digital Core', 'One-command runtime; hosts the shared inference gateway (LiteLLM → Ollama)', 'ours'],
    ['L8', 'Observability & Governance', 'OpenTelemetry traces, API-call ledger, policy decision log, inference metering', 'ours']];

  var views = {};
  views.home = function (el) {
    var j = D.journeys, sf = 0, calls = 0; j.forEach(function (x) { calls += x.calls.length; x.calls.forEach(function (c) { if (c.owner === 'salesforce') sf++; }); });
    el.innerHTML = '<section class="hero"><div><h1>An agentic telco on the Zero Gravity Framework</h1><p>Salesforce Communications Cloud is the <b>system of record only</b> (L6), reached through its out-of-the-box TM Forum Open APIs first, and custom TMF APIs on Salesforce (Apex) only where the org exposes none. ' +
      'Every other layer is our own, built on open source. Agents reason and propose; OPA decides; a BPMN saga executes; every call is traced.</p>' +
      '<div class="kpis"><div><b>' + j.length + '</b><span>recorded journeys</span></div><div><b>' + calls + '</b><span>API calls traced</span></div><div><b>' + sf + '</b><span>calls on Salesforce TMF contracts</span></div><div><b>0</b><span>model calls from L4/L5</span></div></div>' +
      '<button class="btn primary" data-go="journeys">Replay the journeys</button></div>' +
      '<div class="stack">' + LAYERS.map(function (l) { return '<div class="layer ' + l[3] + '"><span class="ln">' + l[0] + '</span><div><b>' + l[1] + '</b><small>' + esc(l[2]) + '</small></div><span class="tag ' + (l[3] === 'salesforce' ? 'sf' : 'ours') + '">' + (l[3] === 'salesforce' ? 'Salesforce SoR' : 'our layer') + '</span></div>'; }).join('') +
      '<div class="layer ext"><span class="ln">+</span><div><b>Inference gateway</b><small>Hosted in L7 runtime, used by L2 agent mesh, governed by L4, metered in L8: our extension of the Zero Gravity framework, not a ninth layer</small></div><span class="tag ours">our extension</span></div></div></section>' +
      '<section class="cards3">' + j.map(function (x, i) { return '<a class="jcard" href="#" data-j="' + i + '"><div class="jt">' + esc(x.title) + '</div>' + badge(x.run.outcome) + '<p>' + esc(x.story) + '</p></a>'; }).join('') + '</section>';
    $$('[data-go]', el).forEach(function (b) { b.onclick = function () { show(b.dataset.go); }; });
    $$('[data-j]', el).forEach(function (a) { a.onclick = function (e) { e.preventDefault(); cur = +a.dataset.j; show('journeys'); }; });
  };

  var cur = 0, viewer = null, timer = null;
  views.journeys = function (el) {
    el.innerHTML = '<div class="jlayout"><aside class="jlist">' + D.journeys.map(function (x, i) { return '<button data-i="' + i + '" class="' + (i === cur ? 'on' : '') + '"><span>' + esc(x.title) + '</span>' + badge(x.run.outcome) + '</button>'; }).join('') + '</aside><section class="jmain" id="jmain"></section></div>';
    $$('.jlist button', el).forEach(function (b) { b.onclick = function () { cur = +b.dataset.i; views.journeys(el); }; });
    renderJourney($('#jmain', el), D.journeys[cur]);
  };

  function renderJourney(el, J) {
    var r = J.run, inf = J.inference || [];
    var sfCalls = J.calls.filter(function (c) { return c.owner === 'salesforce'; }).length;
    el.innerHTML = '<div class="jhead"><div><h2>' + esc(J.title) + '</h2><p class="muted">Run <code>' + esc(J.runId) + '</code> · customer ' + esc(r.customer_id) + ' · ' + esc(fmtDate(r.started_at)) + '</p></div>' + badge(r.outcome) + '</div>' +
      '<blockquote class="utt">“' + esc(r.utterance) + '”</blockquote><p class="story">' + esc(J.story) + '</p>' +
      '<div class="grid2"><div class="card"><div class="ch">Agent reasoning (L2) <button class="btn sm" id="play">▶ Replay</button></div><ol class="steps" id="steps">' +
      r.summary.steps.map(function (s, i) { return '<li data-k="' + i + '"><span class="ln sm">' + esc(s.layer) + '</span><span>' + esc(s.thought) + '</span></li>'; }).join('') + '</ol>' +
      (inf.length ? '<div class="ch sub">Inference gateway routing</div>' + inf.map(function (x) {
        return '<div class="route"><b>' + esc(x.task_class) + '</b> · data: ' + esc(x.data_class) + ' → <b>' + esc(x.routed_model || 'refused') + '</b> via ' + esc(x.served_by) + ' · cache ' + esc(x.cache) + ' · PII redacted ' + esc(x.pii_redacted) + ' · ' + esc(x.latency_ms) + ' ms · £' + Number(x.cost_gbp || 0).toFixed(4) +
          '<div class="opa">' + (x.opa || []).map(function (o) { return '<span class="pill ' + (o.allow ? 'ok' : 'warn') + '">' + esc(o.model) + (o.allow ? ' allowed' : ' denied: ' + esc((o.reasons || []).join('; '))) + '</span>'; }).join(' ') + '</div></div>';
      }).join('') : '') +
      (J.decisions && J.decisions.length ? '<div class="ch sub">Policy decisions (OPA, model consulted: never)</div>' + J.decisions.map(function (d) {
        var x = d.result; return '<div class="route"><b>' + esc(x.gate || 'agent check') + '</b> · policy v' + esc(x.policyVersion) + ' → ' + (x.allow ? '<span class="pill ok">allow</span>' : '<span class="pill warn">deny: ' + esc((x.reasons || []).join(', ')) + '</span>') +
          '<div class="opa">' + (x.checks || []).map(function (c) { return '<span class="pill ' + (c.pass ? 'ok' : 'warn') + '" title="' + esc(c.detail) + '">' + esc(c.id) + ': ' + esc(c.detail) + '</span>'; }).join(' ') + '</div></div>';
      }).join('') : '') + '</div>' +
      '<div class="card"><div class="ch">L5 · BPMN saga on ' + esc(D.stack.l5Engine) + (J.process ? ' · instance <code>' + esc(J.process.processInstanceId.slice(0, 8)) + '…</code> ended at <b>' + esc(J.process.endEvent) + '</b>' : '') + '</div>' +
      (J.process ? '<div id="bpmn" class="bpmn"></div><div class="legend"><span class="lg done"></span>ran <span class="lg comp"></span>compensation <span class="lg cur"></span>replay cursor</div>' : '<p class="muted pad">No saga: the agent stopped before execution (nothing was written to the order systems).</p>') +
      (J.crash ? '<div class="note">Worker pid ' + esc(J.crash.killedPid) + ' killed with SIGKILL mid-TMF641. Service orders created: <b>' + J.crash.serviceOrders.length + '</b>. Saga steps: ' + J.sagaSteps.filter(function (s) { return s.step === 'tmf641-activate'; }).map(function (s) { return esc(s.status) + ' (attempt ' + s.attempt + ')'; }).join(' → ') + '</div>' : '') +
      (J.guardrails ? '<div class="ch sub">Agent identity probes against this live instance</div><table class="t"><tr><th>Attempt</th><th>HTTP</th><th>Result</th></tr>' + J.guardrails.map(function (g) { return '<tr><td>' + esc(g.attempt) + '</td><td>' + g.status + '</td><td>' + (g.result === 'allowed' ? '<span class="pill ok">allowed</span>' : '<span class="pill warn">' + esc(g.result) + '</span>') + '</td></tr>'; }).join('') + '</table>' : '') +
      (J.events.length ? '<div class="ch sub">TMF688 events on Kafka (' + J.events.length + ')</div><ul class="ev">' + J.events.map(function (e) { return '<li><code>' + esc(e.subject) + '</code> <span class="muted">from ' + esc(e.body.source) + '</span></li>'; }).join('') + '</ul>' : '') + '</div></div>' +
      '<div class="card"><div class="ch">Trace · ' + J.calls.length + ' API calls (' + sfCalls + ' on Salesforce TMF contracts) <span class="filters"><label><input type="checkbox" id="f-sf"> Salesforce only</label></span></div>' +
      '<table class="t trace" id="trace"><tr><th>#</th><th>Caller → callee</th><th>Call</th><th>API</th><th>Layer</th><th>ODA block</th><th>Owner / runtime</th><th>HTTP</th></tr>' +
      J.calls.map(function (c, i) { return '<tr data-c="' + i + '" data-o="' + esc(c.owner) + '"><td>' + c.seq + '</td><td>' + esc(c.caller) + ' → ' + esc(c.callee) + '</td><td><code>' + esc(c.method) + ' ' + esc(c.path) + '</code></td><td>' + esc(c.api || '') + '</td><td>' + esc(c.layer || '') + '</td><td>' + esc(c.oda_block || '') + '</td><td>' + ownerTag(c) + '</td><td>' + esc(c.status) + '</td></tr>'; }).join('') + '</table></div>';
    $('#f-sf', el).onchange = function (e) { $$('#trace tr[data-o]', el).forEach(function (tr) { tr.style.display = e.target.checked && tr.dataset.o !== 'salesforce' ? 'none' : ''; }); };
    if (J.process) drawBpmn(J);
    $('#play', el).onclick = function () { replay(el, J); };
  }

  function drawBpmn(J) {
    if (viewer) { try { viewer.destroy(); } catch (e) {} }
    viewer = new window.BpmnJS({ container: '#bpmn' });
    viewer.importXML(D.bpmn).then(function () {
      var canvas = viewer.get('canvas'); canvas.zoom('fit-viewport', 'auto');
      J.process.activities.forEach(function (a) { try { canvas.addMarker(a.activityId, /Cancel|Release|Compensate/.test(a.activityId) ? 'zg-comp' : 'zg-done'); } catch (e) {} });
    });
  }

  function replay(el, J) {
    clearInterval(timer);
    var steps = $$('#steps li', el), rows = $$('#trace tr[data-c]', el), acts = (J.process && J.process.activities) || [];
    steps.forEach(function (s) { s.classList.remove('lit'); }); rows.forEach(function (r) { r.classList.remove('lit'); });
    var canvas = viewer && J.process ? viewer.get('canvas') : null;
    if (canvas) acts.forEach(function (a) { try { canvas.removeMarker(a.activityId, 'zg-done'); canvas.removeMarker(a.activityId, 'zg-comp'); } catch (e) {} });
    var total = Math.max(steps.length, rows.length, acts.length), k = 0;
    timer = setInterval(function () {
      var f = k / total;
      steps.slice(0, Math.ceil(f * steps.length)).forEach(function (s) { s.classList.add('lit'); });
      rows.slice(0, Math.ceil(f * rows.length)).forEach(function (r) { r.classList.add('lit'); });
      if (canvas) acts.slice(0, Math.ceil(f * acts.length)).forEach(function (a) { try { canvas.addMarker(a.activityId, /Cancel|Release|Compensate/.test(a.activityId) ? 'zg-comp' : 'zg-done'); } catch (e) {} });
      if (++k > total) clearInterval(timer);
    }, 120);
  }

  views.coverage = function (el) {
    el.innerHTML = '<h2>Layer coverage: Salesforce vs our layers</h2><p class="muted">Salesforce fit ratings exactly as in “Zero Gravity on Salesforce – Demos v2” (slide 4, How Salesforce maps). The right-hand column is what this demo builds. L4 and L7 are ours.</p>' +
      '<table class="t cov"><tr><th>Layer</th><th>Salesforce capability (v2)</th><th>Fit (v2)</th><th>Demo (v2)</th><th>AgenticTelco builds</th></tr>' +
      D.coverage.map(function (c) { return '<tr><td><span class="ln sm">' + c.layer + '</span> ' + esc(c.name) + '</td><td>' + esc(c.sf) + '</td><td><span class="fit ' + c.fit.toLowerCase().replace(/[^a-z]/g, '') + '">' + esc(c.fit) + '</span></td><td>' + esc(c.demo) + '</td><td>' + esc(c.ours) + '</td></tr>'; }).join('') + '</table>' +
      '<p class="gaps"><b>Gaps (v2):</b> ' + esc(D.coverageGaps) + '</p>';
  };

  views.oda = function (el) {
    var blocks = {}; Object.keys(D.apis).forEach(function (k) { var a = D.apis[k]; (blocks[a.block] = blocks[a.block] || []).push([k, a]); });
    var tagOf = function (a) {
      if (a.owner !== 'salesforce') return a.owner === 'oss' ? ['oss', 'OSS (mocked)'] : ['ours', 'our layer'];
      if (D.stack.sorMode !== 'commscloud') return ['standin', 'Salesforce contract (stand-in)'];
      return a.sfRuntime === 'custom' ? ['sf custom', 'custom TMF API on Salesforce'] : a.sfRuntime === 'OOTB-attempt' ? ['ours', 'OOTB tried, our-layer fallback'] : ['sf', 'Salesforce · OOTB'];
    };
    el.innerHTML = '<h2>ODA functional blocks and the APIs on them</h2><p class="muted">Every traced call carries its ODA block, layer, owner and runtime. OOTB first: TMF629, TMF632 and TMF637 are the org’s native APIs. TMF620, TMF648 and TMF622 are not usable natively on this org, so they are custom TMF APIs on Salesforce (AgenticTelco_ Apex REST). TMF679 is tried natively and falls back to our layer (labelled). TMF921 is not supported by Salesforce, so it is our layer.</p><div class="oda">' +
      Object.keys(blocks).map(function (b) { return '<div class="card"><div class="ch">' + esc(b) + '</div>' + blocks[b].map(function (x) { var a = x[1], t = tagOf(a); return '<div class="api"><b>' + esc(x[0]) + '</b> ' + esc(a.name) + ' <span class="tag ' + t[0] + '">' + esc(t[1]) + '</span> <span class="muted">' + esc(a.layer) + '</span>' + (a.note ? '<small>' + esc(a.note) + '</small>' : '') + '</div>'; }).join('') + '</div>'; }).join('') + '</div>';
  };

  views.guardrails = function (el) {
    var g = D.guardrails, ig = D.inferenceGovernance;
    el.innerHTML = '<h2>Guardrails, proven on the running stack</h2><div class="grid2"><div class="card"><div class="ch">Agents may only START and READ processes (Operaton authorisations)</div><table class="t"><tr><th>Attempt</th><th>HTTP</th><th>Result</th></tr>' +
      g.map(function (x) { return '<tr><td>' + esc(x.attempt) + '</td><td>' + x.status + '</td><td>' + (x.result === 'allowed' ? '<span class="pill ok">allowed</span>' : '<span class="pill warn">rejected</span>') + '</td></tr>'; }).join('') + '</table><p class="muted pad">“Complete” fails on the worker’s lock (400); the authorisation denials are the 403s.</p></div>' +
      '<div class="card"><div class="ch">Inference governance: customer data, reasoning task</div><p class="pad">Routed to <b>' + esc(ig.routedModel) + '</b>, served by ' + esc(ig.servedBy) + ' · PII redacted: ' + ig.piiRedacted + ' · stub: ' + (ig.stub ? 'yes' : 'no') + '</p>' +
      ig.opa.map(function (o) { return '<div class="route"><span class="pill ' + (o.allow ? 'ok' : 'warn') + '">' + esc(o.model) + (o.allow ? ' allowed' : ' denied') + '</span> ' + esc((o.reasons || []).join('; ')) + '</div>'; }).join('') +
      '<div class="ch sub">Policy history (L4) – zero Salesforce changes</div><table class="t"><tr><th>v</th><th>creditMin</th><th>Author</th><th>Reason</th><th>SF calls</th></tr>' + D.policyHistory.map(function (p) { return '<tr><td>' + p.version + '</td><td>' + p.data.creditMin + '</td><td>' + esc(p.author) + '</td><td>' + esc(p.reason) + '</td><td>' + p.salesforce_calls_during_change + '</td></tr>'; }).join('') + '</table></div></div>';
  };

  views.bom = function (el) {
    el.innerHTML = '<h2>Open-source bill of materials</h2><p class="muted">OSI-approved licences only, plus Salesforce as the one commercial component (L6 SoR). Licences as recorded in the architecture pack (06), not legal advice.</p><table class="t"><tr><th>Layer</th><th>Component</th><th>Version</th><th>Licence</th><th>Status here</th></tr>' +
      D.bom.map(function (b) { return '<tr><td>' + esc(b[0]) + '</td><td>' + esc(b[1]) + '</td><td>' + esc(b[2]) + '</td><td>' + esc(b[3]) + '</td><td>' + esc(b[4]) + '</td></tr>'; }).join('') + '</table>';
  };

  function show(v) {
    $$('.gh-tabs button').forEach(function (b) { b.classList.toggle('on', b.dataset.view === v); });
    clearInterval(timer); views[v]($('#view')); window.scrollTo(0, 0);
  }
  $$('.gh-tabs button').forEach(function (b) { b.onclick = function () { show(b.dataset.view); }; });
  window.ZG_SHOW = show;
  show('home');
})();
