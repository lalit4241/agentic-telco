#!/usr/bin/env bash
# AgenticTelco – all tests. Unit tests always run; stack tests need ./run.sh up (they skip otherwise).
# In ZG_SOR_MODE=commscloud the stack tests create AgenticTelco orders/assets in the org (never delete/modify others).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== Python unit tests";            .venv/bin/python -m pytest -q tests/test_unit.py
echo "== OPA policy tests";             .tools/bin/opa test stack/l4_context/policy stack/inference/policy
echo "== Stack tests (live services)";  .venv/bin/python -m pytest -q tests/test_stack.py
if [[ "${ZG_SOR_MODE:-standin}" == "commscloud" ]]; then .venv/bin/python seed/customers/seed_customers.py --reset-inventory >/dev/null; fi
echo "== Web build tests";              (cd web && npm test --silent)
echo "== Playwright e2e";               (cd web && npm run e2e --silent)
