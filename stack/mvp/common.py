"""AgenticTelco MVP shared helpers: config, L3 Postgres access, OpenTelemetry-shaped audit spans, Salesforce calls.

Salesforce is reached only server-side through the Salesforce CLI (stack.zg_common.sf_session): no token is handled here."""
import contextlib, json, os, re, secrets, time
from datetime import datetime, timezone
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
PG_DSN = os.environ.get("ZG_PG_DSN", "postgresql://zg@127.0.0.1:55432/agentictelco")
OPA_URL = os.environ.get("ZG_OPA_URL", "http://127.0.0.1:8181")
OPERATON_URL = os.environ.get("ZG_OPERATON_URL", "http://127.0.0.1:8180/engine-rest")
OLLAMA_URL = os.environ.get("ZG_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("MVP_MODEL", "qwen3-4b-instruct-2507")
PORTS = {"gateway": 8120, "intent": 8121, "context": 8122, "agent": 8123, "mcp": 8124, "standins": 8125}
DEMO_DAY_SECONDS = float(os.environ.get("MVP_DEMO_DAY_SECONDS", "4"))   # demo clock: one business day = 4 s

def url(svc):
    return os.environ.get("MVP_URL_" + svc.upper(), f"http://127.0.0.1:{PORTS[svc]}")

# ---- L3 Postgres ---------------------------------------------------------------------------------------------------
_conn = None
def conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(PG_DSN, autocommit=True, row_factory=dict_row)
    return _conn

def q(sql, *args):
    for attempt in range(2):
        try:
            with conn().cursor() as c:
                c.execute(sql, args)
                return c.fetchall() if c.description else []
        except psycopg.OperationalError:
            global _conn
            _conn = None
            if attempt:
                raise

def q1(sql, *args):
    r = q(sql, *args)
    return r[0] if r else None

def J(v):
    return json.dumps(v, default=str)

def init_schema():
    q((Path(__file__).parent / "schema.sql").read_text())

# ---- trace ids (W3C traceparent, OTel shape) ----------------------------------------------------------------------
def new_trace():
    return secrets.token_hex(16)

def new_span():
    return secrets.token_hex(8)

def traceparent(trace_id, span_id):
    return f"00-{trace_id}-{span_id}-01"

def parse_traceparent(h):
    try:
        _, t, s, _ = (h or "").split("-")
        return t, s
    except ValueError:
        return None, None

def _trim(v, n=6000):
    if v is None:
        return None
    s = J(v)
    return v if len(s) <= n else {"truncated": s[:n]}

class Span:
    """One audit row. Use as a context manager; set .status / .response / .attrs inside."""
    def __init__(self, trace_id, layer, component, step, runtime="ours", api=None, method=None, path=None, parent=None,
                 conversation_id=None, request=None, attrs=None):
        self.trace_id, self.layer, self.component, self.step, self.runtime = trace_id, layer, component, step, runtime
        self.api, self.method, self.path, self.parent, self.conversation_id = api, method, path, parent, conversation_id
        self.request, self.attrs, self.status, self.response = request, dict(attrs or {}), None, None
        self.span_id = new_span()

    def __enter__(self):
        self.t0, self.start = time.perf_counter(), datetime.now(timezone.utc)
        return self

    def __exit__(self, et, ev, tb):
        if et is not None:
            self.status = self.status or 500
            self.attrs["error"] = str(ev)[:300]
        end = datetime.now(timezone.utc)
        try:
            q("""insert into mvp.audit(trace_id, span_id, parent_span_id, conversation_id, layer, component, step, runtime, api, method, path, status,
                 start_ts, end_ts, duration_ms, attributes, request, response) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              self.trace_id, self.span_id, self.parent, self.conversation_id, self.layer, self.component, self.step, self.runtime, self.api,
              self.method, self.path, self.status, self.start, end, round((time.perf_counter() - self.t0) * 1000, 1), J(self.attrs),
              J(_trim(self.request)), J(_trim(self.response)))
        except Exception as e:   # audit must never break the journey; it is reported in the log
            print("audit write failed:", e, flush=True)
        return False

def audit(trace_id, layer, component, step, **kw):
    with Span(trace_id, layer, component, step, **kw):
        pass

# ---- Salesforce (server-side, via the Salesforce CLI) -------------------------------------------------------------
from stack.zg_common.sf_session import request as _sf_request, API_V   # noqa: E402
SF_DATA = f"/services/data/{API_V}"
NATIVE = "native Salesforce API"
FACADE = "TMF facade within Salesforce (Apex)"
STANDIN = "Legacy stand-in (mocked)"

def sf(trace_id, step, method, path, body=None, runtime=NATIVE, api=None, layer="L6", component="Salesforce", parent=None):
    with Span(trace_id, layer, component, step, runtime=runtime, api=api, method=method, path=path, parent=parent, request=body) as sp:
        r = _sf_request(method, path, body)
        sp.status, sp.response = r.status_code, r.json()
        return r

_SFID = re.compile(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?")
_SFID_SUFFIX = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def sf_id(value, field="id"):
    """Return value if it is a valid 15- or 18-character Salesforce ID, else raise ValueError.
    Every ID that goes into a SOQL string passes through here first, so a crafted value can't change the query.
    For 18-character IDs the 3-character case-safe suffix is checked too."""
    if not isinstance(value, str) or not _SFID.fullmatch(value):
        raise ValueError(f"{field}: not a valid Salesforce ID")
    if len(value) == 18:
        suffix = ""
        for i in range(3):
            chunk = value[i * 5:(i + 1) * 5]
            suffix += _SFID_SUFFIX[sum(1 << j for j, ch in enumerate(chunk) if ch.isupper())]
        if value[15:] != suffix:
            raise ValueError(f"{field}: not a valid Salesforce ID (checksum)")
    return value


_SAFE_KEY = re.compile(r"[A-Za-z0-9-]{1,64}")
_SOQL_DT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def safe_key(value, field="key"):
    """Business keys we generate ourselves (e.g. MVP-60744BC6): letters, digits and hyphens only."""
    if not isinstance(value, str) or not _SAFE_KEY.fullmatch(value):
        raise ValueError(f"{field}: not a valid business key")
    return value


def soql_datetime(value, field="datetime"):
    """ISO date-time cut to seconds, for a SOQL literal (YYYY-MM-DDTHH:MM:SS)."""
    v = (value or "")[:19]
    if not _SOQL_DT.fullmatch(v):
        raise ValueError(f"{field}: not an ISO date-time")
    return v


def soql(trace_id, step, query, api=None):
    from urllib.parse import quote
    r = sf(trace_id, step, "GET", f"{SF_DATA}/query?q=" + quote(query), api=api)
    if r.status_code != 200:
        raise RuntimeError(f"SOQL failed {r.status_code}: {r.text[:200]}")
    return r.json()["records"]

def brightwell():
    return json.loads((ROOT / "seed" / "customers" / "brightwell.json").read_text())

def copy_json():
    p = ROOT / "web" / "src" / "mvp" / "copy.json"
    return json.loads(p.read_text()) if p.exists() else {"layers": [], "glossary": []}
