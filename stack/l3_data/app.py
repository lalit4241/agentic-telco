"""L3 · Data Foundations (our layer): governed data products + a pgvector knowledge index.
Credit and usage are data products owned outside the SoR; network capacity is a federated (zero-copy) view of OSS inventory."""
import hashlib, math, re
from fastapi import FastAPI, HTTPException
from stack.zg_common.db import q, q1
from stack.zg_common.telemetry import instrument_app

SVC = "l3-data"
app = FastAPI(title="AgenticTelco L3 data products")
instrument_app(app, SVC)
B = "/zg/data/v1"

KNOWLEDGE = [
    ("KB-1", "Full fibre upgrade journey", "Upgrading from Fibre 150 to Full Fibre 900 needs FTTP at the premises and a free OLT port at the exchange. A new Wi-Fi 7 hub ships for gigabit tiers."),
    ("KB-2", "Slow speeds on FTTC/FTTP", "If sync rate is far below the plan speed, run a line test (TMF645). Low optical power on FTTP suggests a dirty connector or a bent fibre; raise a field service order (TMF641)."),
    ("KB-3", "Home working households", "Households with many devices and work-from-home usage over 800 GB per month typically benefit from 500 Mb/s or more."),
    ("KB-4", "Consent for marketing offers", "Proactive upgrade offers need marketing consent. Operator policy may require consent captured on a digital channel."),
    ("KB-5", "Order fallout", "If service activation fails after the commercial order is placed, the order must be cancelled and any reserved network capacity released."),
]

def embed(text, dim=64):
    """Deterministic hashed bag-of-words embedding (no model download needed) – stored in pgvector."""
    v = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return "[" + ",".join(f"{x / n:.5f}" for x in v) + "]"

@app.on_event("startup")
def seed():
    for k, t, b in KNOWLEDGE:
        q("insert into l3.knowledge values(%s,%s,%s,%s::vector) on conflict(id) do update set body=excluded.body, embedding=excluded.embedding", k, t, b, embed(t + " " + b))

@app.get("/health")
def health():
    return {"ok": True, "service": SVC}

@app.get(B + "/creditProfile/{cid}")
def credit(cid: str):
    r = q1("select * from l3.credit_score where customer_id=%s", cid)
    if not r:
        raise HTTPException(404)
    return {"customerId": cid, "score": r["score"], "bureau": r["bureau"], "asOf": str(r["as_of"]), "dataProduct": "credit-profile v1", "owner": "Finance data domain"}

@app.get(B + "/usage/{cid}")
def usage(cid: str):
    r = q1("select * from l3.usage where customer_id=%s", cid)
    if not r:
        raise HTTPException(404)
    return {"customerId": cid, "avgMonthlyGB": r["avg_monthly_gb"], "peakMbps": r["peak_mbps"], "devices": r["devices"], "workFromHome": r["wfh"], "dataProduct": "usage-insights v1"}

@app.get(B + "/networkCapacity/{exchange}")
def capacity(exchange: str):
    r = q1("select * from oss.capacity where exchange=%s", exchange)
    if not r:
        raise HTTPException(404)
    return {"exchange": exchange, "portsTotal": r["ports_total"], "portsReserved": r["ports_reserved"], "utilisation": float(r["utilisation"]),
            "dataProduct": "network-capacity v1 (federated from OSS inventory, zero copy)"}

@app.get(B + "/knowledge/search")
def search(q_: str = "", k: int = 2, query: str | None = None):
    text = query or q_
    rows = q("select id, title, body, 1 - (embedding <=> %s::vector) as score from l3.knowledge order by embedding <=> %s::vector limit %s", embed(text), embed(text), k)
    return [{"id": r["id"], "title": r["title"], "body": r["body"], "score": round(float(r["score"]), 3)} for r in rows]
