"""L1 · read-only GraphQL BFF over our own services (Strawberry, MIT) – ADR-008.
Reads only: customer view (via TMF REST reads), runs, API-call ledger, BPMN process state, policy, inference usage.
There is deliberately NO Mutation type: all SoR writes stay on TMF REST, called only by L5 BPMN tasks."""
from typing import Optional
import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON
from fastapi import FastAPI
from stack.zg_common.config import SOR_BASE, url
from stack.zg_common.db import q, q1
from stack.zg_common.http import call

C = "l1-graphql"

@strawberry.type
class Product:
    id: str; name: str; status: str

@strawberry.type
class Customer:
    id: str; name: str; exchange: Optional[str]; consentChannel: Optional[str]
    @strawberry.field
    def products(self) -> list[Product]:
        rows = call(C, "GET", f"{SOR_BASE}/tmf-api/productInventory/v4/product", params={"customerId": self.id}).json()
        return [Product(id=r["id"], name=r["name"], status=r["status"]) for r in rows]

@strawberry.type
class ApiCall:
    seq: int; caller: str; callee: str; method: str; path: str; status: Optional[int]; api: Optional[str]
    layer: Optional[str]; odaBlock: Optional[str]; owner: Optional[str]; runtime: Optional[str]

@strawberry.type
class Run:
    runId: str; scenario: Optional[str]; title: Optional[str]; customerId: Optional[str]; outcome: Optional[str]
    @strawberry.field
    def calls(self, owner: Optional[str] = None) -> list[ApiCall]:
        rows = q("select * from l8.api_calls where run_id=%s and (%s::text is null or owner=%s) order by seq", self.runId, owner, owner)
        return [ApiCall(seq=r["seq"], caller=r["caller"], callee=r["callee"], method=r["method"], path=r["path"], status=r["status"], api=r["api"],
                        layer=r["layer"], odaBlock=r["oda_block"], owner=r["owner"], runtime=r["runtime"]) for r in rows]
    @strawberry.field
    def salesforceCalls(self) -> int:
        return q1("select count(*) n from l8.api_calls where run_id=%s and owner='salesforce'", self.runId)["n"]
    @strawberry.field
    def process(self) -> Optional[JSON]:
        s = q1("select workflow_id from l5.saga where run_id=%s order by created_at desc limit 1", self.runId)
        return call(C, "GET", url("l5_orchestrator") + f"/zg/orchestrator/v1/process/{s['workflow_id']}").json() if s else None
    @strawberry.field
    def inference(self) -> JSON:
        return [dict(r, cost_gbp=float(r["cost_gbp"] or 0), latency_ms=float(r["latency_ms"] or 0), at=str(r["at"]))
                for r in q("select * from l8.inference where run_id=%s order by seq", self.runId)]

def _run(r):
    return Run(runId=r["run_id"], scenario=r["scenario"], title=r["title"], customerId=r["customer_id"], outcome=r["outcome"])

@strawberry.type
class Query:
    @strawberry.field
    def customer(self, id: str) -> Optional[Customer]:
        r = call(C, "GET", f"{SOR_BASE}/tmf-api/customerManagement/v4/customer/{id}")
        if r.status_code != 200:
            return None
        c = r.json()
        ch = c["contactMedium"][0]["characteristic"]
        p = call(C, "GET", f"{SOR_BASE}/tmf-api/partyManagement/v4/individual/{c['engagedParty']['id']}").json()
        consent = next((x["value"] for x in p.get("partyCharacteristic", []) if x["name"] == "marketingConsent"), {})
        return Customer(id=id, name=c["name"], exchange=ch.get("exchange"), consentChannel=consent.get("channel"))
    @strawberry.field
    def runs(self, limit: int = 20) -> list[Run]:
        return [_run(r) for r in q("select * from l8.runs order by started_at desc limit %s", limit)]
    @strawberry.field
    def run(self, runId: str) -> Optional[Run]:
        r = q1("select * from l8.runs where run_id=%s", runId)
        return _run(r) if r else None
    @strawberry.field
    def policy(self) -> JSON:
        return call(C, "GET", url("l4_context") + "/zg/context/v1/policy").json()

schema = strawberry.Schema(query=Query)  # no mutation type – read-only by construction (ADR-008)
app = FastAPI(title="AgenticTelco read-only GraphQL (Strawberry)")
app.include_router(GraphQLRouter(schema), prefix="/graphql")

@app.get("/health")
def health():
    return {"ok": True, "service": C, "mutations": False}
