"""AgenticTelco MVP shared helpers: config, L3 Postgres access, OpenTelemetry-shaped audit spans, Salesforce calls.

Salesforce is reached only server-side (Salesforce CLI session, no token handled here) and only through TM Forum Open API paths."""
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
APEX = "/services/apexrest/agentictelco"          # TMF facade within Salesforce (Apex classes AgenticTelco_TMFnnn)
CC = f"{SF_DATA}/connect/comms"                    # Salesforce's own TMF Open APIs (Communications Cloud)
TMF_SF = "TMF Open API (Salesforce)"               # the on-screen chip for every Salesforce call
OOTB = "Salesforce (out of the box)"               # 'Provided by' (detail drawer only)
FACADE = "TMF facade within Salesforce (Apex)"     # 'Provided by' (detail drawer only)
STANDIN = "Legacy stand-in (mocked)"
TMF_NAMES = {"TMF620": "Product Catalog", "TMF622": "Product Order", "TMF629": "Customer", "TMF632": "Party", "TMF637": "Product Inventory", "TMF639": "Resource Inventory",
             "TMF641": "Service Order", "TMF648": "Quote", "TMF666": "Account", "TMF671": "Promotion", "TMF679": "Product Offering Qualification",
             "TMF921": "Intent"}


def tmf(tag):
    """'TMF622' -> 'TMF622 Product Order'."""
    return f"{tag} {TMF_NAMES[tag]}"


def provided_by(path):
    """Everything above L6 reaches Salesforce only through TM Forum Open APIs: Salesforce's own (connect/comms) or the
    AgenticTelco TMF facade (apexrest/agentictelco). Any other Salesforce path (SOQL, sObject REST) is refused here."""
    p = (path or "").split("?")[0]
    if p.startswith(APEX + "/tmf"):
        return FACADE
    if p.startswith(CC + "/"):
        return OOTB
    raise ValueError(f"not a TM Forum Open API path: {p}")


def sf(trace_id, step, method, path, body=None, api=None, layer="L6", component="Salesforce", parent=None):
    """One Salesforce call through a TMF Open API. api is the TMF tag, e.g. 'TMF622'."""
    by = provided_by(path)
    with Span(trace_id, layer, component, step, runtime=TMF_SF, api=tmf(api), method=method, path=path, parent=parent, request=body,
              attrs={"providedBy": by, "tmf": api}) as sp:
        r = _sf_request(method, path, body)
        sp.status, sp.response = r.status_code, r.json()
        return r


def sf_unaudited(method, path, body=None):
    """Same TMF-only guard as sf(), without an audit span: used only to reset the demo between runs (outside any journey)."""
    provided_by(path)
    return _sf_request(method, path, body)


_SECRET_KEY = re.compile(r"^(?:(?:access|refresh|id|bearer|api)?_?token|session_?id|sid|(?:set-)?cookie)$|authori[sz]ation|password|secret|frontdoor", re.I)
_SESSION = re.compile(r"\b00D[A-Za-z0-9]{12,15}![A-Za-z0-9._-]+")
_SF_HOST = re.compile(r"https?://[A-Za-z0-9.-]+\.(?:my\.)?(?:salesforce|force|cloudforce|salesforce-setup|visualforce)\.com[^\s\"']*")


def _redact_str(v):
    v = _SESSION.sub("[redacted]", v)
    def host(m):
        u = m.group(0)
        if "/lightning/r/" in u and "frontdoor" not in u and "sid=" not in u:
            return u            # a Lightning record link is fine (opening it needs the viewer's own login)
        return "[instance]" + re.sub(r"^https?://[^/]+", "", u).split("?")[0]
    return _SF_HOST.sub(host, v)


def redact(v):
    """Redacted copy for the UI and recordings: no tokens, session ids, login/frontdoor or instance URLs (record links stay)."""
    if isinstance(v, dict):
        return {k: ("[redacted]" if _SECRET_KEY.search(str(k)) else redact(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [redact(x) for x in v]
    if isinstance(v, str):
        return _redact_str(v)
    return v


def tmf_ok(r, what):
    if r.status_code >= 300:
        raise RuntimeError(f"{what} failed {r.status_code}: {r.text[:300]}")
    return r.json()

_SFID = re.compile(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?")
_SFID_SUFFIX = "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def sf_id(value, field="id"):
    """Return value if it is a valid 15- or 18-character Salesforce ID, else raise ValueError.
    Every ID that goes into a TMF API path or filter passes through here first, so a crafted value can't change the call.
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


def safe_key(value, field="key"):
    """Business keys we generate ourselves (e.g. MVP-60744BC6): letters, digits and hyphens only."""
    if not isinstance(value, str) or not _SAFE_KEY.fullmatch(value):
        raise ValueError(f"{field}: not a valid business key")
    return value


def brightwell():
    return json.loads((ROOT / "seed" / "customers" / "brightwell.json").read_text())

def copy_json():
    p = ROOT / "web" / "src" / "mvp" / "copy.json"
    return json.loads(p.read_text()) if p.exists() else {"layers": [], "glossary": []}
