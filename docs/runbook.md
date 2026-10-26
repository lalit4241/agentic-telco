# AgenticTelco runbook

## Prerequisites (native run, as recorded)

| Tool | Version used | Where |
|---|---|---|
| Python + uv | 3.13 | `./run.sh setup` creates `.venv` and `.venv-litellm` (LiteLLM needs mcp 2.x; our MCP tools use 1.x) |
| PostgreSQL + pgvector | 17.11 / 0.8.0 | `PG_BIN` (default `/usr/lib/postgresql/17/bin`) |
| Java | OpenJDK 21 | `.tools/jre` |
| Operaton | 2.2.0 (Run distribution) | `.tools/operaton` |
| Apache Kafka | 4.4.0 (KRaft) | `.tools/kafka` |
| OPA | 1.21.4 | `.tools/bin/opa` |
| Ollama + `qwen2.5:0.5b` | 0.40.11 | `.tools/ollama` (models in `.tools/ollama/models`) |
| Node.js | 22 | `web/` (`npm ci`; Playwright uses a system Chromium through playwright-core) |
| Salesforce CLI | `sf` with alias `sfcomms` | Real-org mode only. You sign in yourself (`sf org login web -a sfcomms`); the stack never sees a password or token |

`.tools/`, `.data/`, the venvs and `node_modules` are git-ignored.

## Start and stop

```bash
./run.sh up                         # stand-in SoR on :8106
ZG_SOR_MODE=commscloud ./run.sh up  # real org: L2/L4/L5 talk to the L6 Salesforce adapter on :8116 (Operaton lock 30 s)
./run.sh down
./run.sh reset                      # wipes local Postgres/Kafka data (not the org)
```

The logs are in `.data/stack.log` (honcho). Secrets are generated on first start into `.data/secrets.env` (mode 600):

- Operaton admin, agent and worker identities.
- The LiteLLM master key.

## Ports

| Port | Service | Layer |
|---|---|---|
| 8102 | Agent mesh + TMF921 intent API | L1/L2 |
| 8103 | Data products | L3 |
| 8104 | Context and policy API (in front of OPA :8181) | L4 |
| 8105 | Read-only L5 view (Operaton REST on :8180) | L5 |
| 8106 | TMF stand-in (same /tmf-api paths) | L6 (stand-in) |
| **8116** | **Salesforce adapter**: OOTB + custom TMF APIs on Salesforce, using the sf CLI session | L6 (real org) |
| 8107 | OSS mock (TMF641/645/621) | L6 (OSS) |
| 8108 | A2A network agent | L2 |
| 8110 | Inference gateway → LiteLLM :4000 → Ollama :11434 | L7 |
| 8111 | GraphQL (Strawberry, read-only) | L1 |
| 55432 / 9092 | PostgreSQL / Kafka | L3 |

## Real-org operations (`sfcomms`)

These commands are **read-only**:

| Command | What it does |
|---|---|
| `.venv/bin/python scripts/verify_org.py` | Capability probe (GET plus one GraphQL read). Writes `docs/api/org-capabilities.json` |

These commands **create AgenticTelco records only**:

| Command | What it does |
|---|---|
| `.venv/bin/python seed/epc/seed_epc.py` | Seeds the EPC catalogue (idempotent) |
| `.venv/bin/python seed/customers/seed_customers.py [--reset-inventory]` | Seeds the four demo customers, and with the flag resets the demo inventory |
| `cd salesforce && sf project deploy start --target-org sfcomms --source-dir force-app --test-level RunSpecifiedTests --tests AgenticTelco_TmfTest` | Deploys the Apex classes |

- **Safety:** the adapter refuses DELETE (`stack/zg_common/sf_session.py`). The Apex PATCH endpoints act only on AgenticTelco records.
- **Recording a run:** `ZG_SOR_MODE=commscloud ./run.sh journeys` first resets the demo inventory, then records all nine
  journeys into `recordings/run-<date>.json`. It also updates `recordings/latest.json`.

## Build and preview the page

```bash
cd web && npm ci
node build.js              # reads $TF_DEMO_PASSWORD or ../.demo-password (git-ignored, mode 600); never prints it
npm test && node test/e2e.js   # e2e also writes docs/home.png and docs/journey.png
python3 -m http.server -d dist 8099   # preview at http://127.0.0.1:8099
```

- **Publishing:** `.github/workflows/pages.yml` builds the page on push to `main`. It needs the repo secret `DEMO_PASSWORD`,
  and the Pages source must be set to GitHub Actions.
- **Password:** rotate it after events. Client-side encryption can be attacked offline, so use a long random password.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Starting… waiting` never ends | Check `.data/stack.log` for Operaton or Kafka start-up errors. Java must be 17 or later |
| Adapter returns 502 | The sf CLI session has expired. Sign in again with `sf org login web -a sfcomms` (you do this yourself) |
| TMF679 shows "our layer" | Expected: the org has no default qualification procedure. The adapter never changes org setup |
| Crash-resume journey slow | In commscloud mode the Operaton lock is 30 s (`ZG_LOCK_MS`), so the re-delivery waits for it |
