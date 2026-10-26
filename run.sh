#!/usr/bin/env bash
# AgenticTelco – one-command start for the open-source Zero Gravity stack.
#   ./run.sh setup     create the Python venvs (needs uv, Java 17+, PostgreSQL 17 + pgvector; tools in .tools/)
#   ./run.sh up        initialise (first time) and start everything under honcho (logs: .data/stack.log)
#   ./run.sh down      stop everything
#   ./run.sh journeys  record the demo journeys into recordings/
#   ./run.sh test      unit + policy + engine guardrail + crash/resume + e2e tests
set -euo pipefail
cd "$(dirname "$0")"
export PG_BIN=${PG_BIN:-/usr/lib/postgresql/17/bin}
mkdir -p .data
if [[ ! -f .data/secrets.env ]]; then   # generated locally, git-ignored, never shipped
  {
    echo "ZG_OPERATON_ADMIN_USER=zgadmin"
    echo "ZG_OPERATON_ADMIN_PASSWORD=$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
    echo "ZG_OPERATON_AGENT_USER=zgagent"
    echo "ZG_OPERATON_AGENT_PASSWORD=$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
    echo "ZG_OPERATON_WORKER_USER=zgl5worker"
    echo "ZG_OPERATON_WORKER_PASSWORD=$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
    echo "LITELLM_MASTER_KEY=sk-zg-$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
  } > .data/secrets.env
  chmod 600 .data/secrets.env
fi
set -a; . .data/secrets.env; set +a
# Real org: ZG_SOR_MODE=commscloud ./run.sh up  → L2/L4/L5 use the L6 Salesforce adapter (port 8116, sf CLI alias sfcomms)
if [[ "${ZG_SOR_MODE:-standin}" == "commscloud" ]]; then
  export ZG_SOR_BASE=${ZG_SOR_BASE:-http://127.0.0.1:8116} ZG_LOCK_MS=${ZG_LOCK_MS:-30000}
fi

init_pg() {
  if [[ ! -d .data/pg ]]; then
    "$PG_BIN/initdb" -D .data/pg -U zg --auth=trust -E UTF8 >/dev/null
    "$PG_BIN/pg_ctl" -D .data/pg -o "-p 55432 -k /tmp -c listen_addresses=127.0.0.1" -w start >/dev/null
    "$PG_BIN/createdb" -h 127.0.0.1 -p 55432 -U zg agentictelco
    "$PG_BIN/createdb" -h 127.0.0.1 -p 55432 -U zg operaton
    "$PG_BIN/psql" -q -h 127.0.0.1 -p 55432 -U zg agentictelco -f stack/db/schema.sql -f stack/db/seed.sql
    "$PG_BIN/pg_ctl" -D .data/pg -w stop >/dev/null
  fi
}

case "${1:-up}" in
  setup)
    uv venv -q -p 3.13 .venv && uv pip install -q --python .venv/bin/python -r requirements.txt
    uv venv -q -p 3.13 .venv-litellm && uv pip install -q --python .venv-litellm/bin/python -r requirements-litellm.txt
    uv pip uninstall -q --python .venv-litellm/bin/python litellm-enterprise || true   # MIT core only
    echo "venvs ready. Tools expected in .tools/: jre (17+), operaton 2.2.0, kafka 4.4.0, bin/opa, ollama – see docs/runbook.md" ;;
  up)
    init_pg
    mkdir -p .data/otel
    if [[ ! -f .data/kafka/meta.properties ]]; then
      JAVA_HOME=$PWD/.tools/jre .tools/kafka/bin/kafka-storage.sh format --standalone -t "$(JAVA_HOME=$PWD/.tools/jre .tools/kafka/bin/kafka-storage.sh random-uuid)" \
        -c stack/l3_data/kafka/server.properties >/dev/null
    fi
    cp stack/l5_orchestrator/operaton/production.yml .tools/operaton/configuration/production.yml
    nohup .venv/bin/honcho start -f Procfile > .data/stack.log 2>&1 &
    echo $! > .data/honcho.pid
    echo "Starting… waiting for Operaton + services"; PG_BIN=$PG_BIN scripts/wait_for.sh pg kafka opa operaton
    .venv/bin/python -m stack.l5_orchestrator.bootstrap
    for p in 8102 8103 8104 8105 8106 8107 8108 8110 8111 8116; do
      for i in $(seq 1 60); do curl -sf 127.0.0.1:$p/health >/dev/null && break; sleep 1; done
    done
    echo "Stack up. L2 TMF921: http://127.0.0.1:8102/tmf-api/intentManagement/v4/intent · Operaton: http://127.0.0.1:8180/engine-rest"
    ;;
  down)
    [[ -f .data/honcho.pid ]] && kill "$(cat .data/honcho.pid)" 2>/dev/null || true
    sleep 3; .tools/operaton/shutdown.sh >/dev/null 2>&1 || true
    pkill -f "honcho start -f Procfile" 2>/dev/null || true
    for i in $(seq 1 30); do (exec 3<>/dev/tcp/127.0.0.1/55432) 2>/dev/null || break; sleep 1; done   # wait for Postgres to exit
    ;;
  journeys)
    if [[ "${ZG_SOR_MODE:-standin}" == "commscloud" ]]; then .venv/bin/python seed/customers/seed_customers.py --reset-inventory; fi
    .venv/bin/python scripts/run_journeys.py ;;
  test) scripts/test_all.sh ;;
  reset)
    "$0" down || true; rm -rf .data/pg .data/kafka .data/kafka-logs .data/otel .data/stack.log; echo "reset done" ;;
  *) echo "usage: $0 up|down|journeys|test|reset"; exit 1 ;;
esac
