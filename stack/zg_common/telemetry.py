"""L8: OpenTelemetry spans exported to a JSONL file, plus an API-call ledger in Postgres (schema l8)."""
import contextvars, json, os, threading, time
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from .config import DATA
from . import registry
from .db import q, J

RUN_ID = contextvars.ContextVar("zg_run_id", default=None)
SPAN_FILE = DATA / "otel" / "spans.jsonl"
_lock = threading.Lock()

class JsonlExporter(SpanExporter):
    def export(self, spans):
        SPAN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(SPAN_FILE, "a") as f:
            for s in spans:
                ctx = s.get_span_context()
                f.write(json.dumps({
                    "trace_id": format(ctx.trace_id, "032x"), "span_id": format(ctx.span_id, "016x"),
                    "parent_id": format(s.parent.span_id, "016x") if s.parent else None,
                    "name": s.name, "service": s.resource.attributes.get("service.name"),
                    "start_ns": s.start_time, "end_ns": s.end_time,
                    "duration_ms": round((s.end_time - s.start_time) / 1e6, 2),
                    "status": s.status.status_code.name,
                    "attributes": {k: v for k, v in (s.attributes or {}).items()},
                }) + "\n")
        return SpanExportResult.SUCCESS
    def shutdown(self):
        pass

_configured = False
def setup(service_name):
    global _configured
    if not _configured:
        tp = TracerProvider(resource=Resource.create({"service.name": service_name, "zg.stack": "agentictelco"}))
        tp.add_span_processor(SimpleSpanProcessor(JsonlExporter()))
        # Optional OTLP/HTTP export (L8): Jaeger and/or Langfuse MIT core (/api/public/otel). Off unless env is set.
        ep = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if ep:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor
                tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            except Exception as e:
                print("OTLP exporter not available:", e)
        trace.set_tracer_provider(tp)
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
        except Exception:
            pass
        _configured = True
    return trace.get_tracer(service_name)

def current_trace_id():
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None

def record_call(*, caller, callee, method, path, status, req=None, resp=None, ms=None, run_id=None, extra=None, runtime=None):
    """Write one API call to the L8 ledger, tagged with layer / ODA block / owner / runtime."""
    from .config import SOR_MODE
    key = registry.api_for(path)
    a = registry.APIS.get(key, {})
    live = tuple(os.environ.get("ZG_SOR_LIVE_APIS", "").split(",")) if SOR_MODE == "commscloud" else ()
    q("""insert into l8.api_calls(run_id, trace_id, caller, callee, method, path, status, api, api_name, layer,
          oda_block, owner, runtime, sf_certified, note, request, response, duration_ms, extra)
         values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
      run_id or RUN_ID.get(), current_trace_id(), caller, callee, method, path, status, key, a.get("name"),
      a.get("layer"), a.get("block"), a.get("owner"), runtime or registry.runtime_tag(key, SOR_MODE, live),
      bool(a.get("certified")), a.get("note"), J(req), J(resp), ms, J(extra or {}))

def instrument_app(app, service_name, record_inbound=True):
    """FastAPI: OTel server spans + inbound call ledger (callee-side, so every caller is captured)."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from starlette.requests import Request
    from starlette.responses import Response
    setup(service_name)
    FastAPIInstrumentor.instrument_app(app)

    @app.middleware("http")
    async def zg_ledger(request: Request, call_next):
        rid = request.headers.get("x-zg-run-id")
        tok = RUN_ID.set(rid) if rid else None
        body = await request.body()
        t0 = time.perf_counter()
        resp = await call_next(request)
        chunks = [c async for c in resp.body_iterator]
        raw = b"".join(chunks)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        p = request.url.path
        if record_inbound and rid and not p.startswith(("/health", "/docs", "/openapi")):
            def parse(b):
                try:
                    return json.loads(b) if b else None
                except Exception:
                    return b[:500].decode("utf-8", "replace")
            try:
                record_call(caller=request.headers.get("x-zg-caller", "client"), callee=service_name,
                            method=request.method, path=p + (("?" + request.url.query) if request.url.query else ""),
                            status=resp.status_code, req=parse(body), resp=parse(raw), ms=ms, run_id=rid,
                            runtime=resp.headers.get("x-zg-runtime"),
                            extra={"salesforceCalls": parse(resp.headers["x-zg-sf-calls"].encode()), "org": resp.headers.get("x-zg-sf-org"),
                                   "enrichment": resp.headers.get("x-zg-enrichment")} if resp.headers.get("x-zg-sf-calls") else None)
            except Exception as e:  # ledger must never break the business call
                print("ledger error", e)
        if tok:
            RUN_ID.reset(tok)
        return Response(content=raw, status_code=resp.status_code, headers=dict(resp.headers), media_type=resp.media_type)
