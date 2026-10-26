# AgenticTelco · Zero Gravity stack – native (no Docker) variant of docker-compose.yml. Start with ./run.sh up
postgres:   exec "$PG_BIN/postgres" -D .data/pg -p 55432 -k /tmp -c listen_addresses=127.0.0.1
kafka:      JAVA_HOME=$PWD/.tools/jre KAFKA_HEAP_OPTS="-Xmx384m -Xms128m" LOG_DIR=$PWD/.data/kafka-logs exec .tools/kafka/bin/kafka-server-start.sh stack/l3_data/kafka/server.properties
opa:        exec .tools/bin/opa run --server --addr 127.0.0.1:8181 --log-level error stack/l4_context/policy/upgrade.rego stack/inference/policy/models.rego stack/inference/policy/models.json
ollama:     OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=.tools/ollama/models exec .tools/ollama/bin/ollama serve
operaton:   scripts/wait_for.sh pg && JAVA_HOME=$PWD/.tools/jre exec .tools/operaton/internal/run.sh start --rest --production
litellm:    exec .venv-litellm/bin/litellm --config stack/inference/litellm.yaml --host 127.0.0.1 --port 4000
l8-events:  scripts/wait_for.sh pg kafka && exec .venv/bin/python -m stack.l8_observe.event_recorder
l3-data:    scripts/wait_for.sh pg && exec .venv/bin/uvicorn stack.l3_data.app:app --host 127.0.0.1 --port 8103 --log-level warning
l4-context: scripts/wait_for.sh pg opa && exec .venv/bin/uvicorn stack.l4_context.app:app --host 127.0.0.1 --port 8104 --log-level warning
l6-sor:     scripts/wait_for.sh pg kafka && exec .venv/bin/uvicorn stack.l6_sor_standin.app:app --host 127.0.0.1 --port 8106 --log-level warning
l6-sf:      exec .venv/bin/uvicorn stack.l6_salesforce_adapter.app:app --host 127.0.0.1 --port 8116 --log-level warning
oss-mock:   scripts/wait_for.sh pg kafka && exec .venv/bin/uvicorn stack.oss_mock.app:app --host 127.0.0.1 --port 8107 --log-level warning
net-agent:  scripts/wait_for.sh pg && exec .venv/bin/uvicorn stack.l2_mesh.network_agent:app --host 127.0.0.1 --port 8108 --log-level warning
mcp-tools:  scripts/wait_for.sh pg && exec .venv/bin/python -m stack.l2_mesh.mcp_tools
inference:  scripts/wait_for.sh pg opa && exec .venv/bin/uvicorn stack.inference.app:app --host 127.0.0.1 --port 8110 --log-level warning
graphql:    scripts/wait_for.sh pg && exec .venv/bin/uvicorn stack.l1_web.graphql_api:app --host 127.0.0.1 --port 8111 --log-level warning
l2-mesh:    scripts/wait_for.sh pg operaton && exec .venv/bin/uvicorn stack.l2_mesh.app:app --host 127.0.0.1 --port 8102 --log-level warning
l5-workers: scripts/wait_for.sh pg operaton && exec scripts/supervise.sh .data/l5-worker.pid .venv/bin/python -m stack.l5_orchestrator.workers
l5-api:     scripts/wait_for.sh pg operaton && exec .venv/bin/uvicorn stack.l5_orchestrator.app:app --host 127.0.0.1 --port 8105 --log-level warning
