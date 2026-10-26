#!/usr/bin/env bash
# wait_for.sh pg kafka opa operaton … – block until dependencies answer (max ~180 s)
for dep in "$@"; do
  for i in $(seq 1 180); do
    case $dep in
      pg)       "$PG_BIN/pg_isready" -h 127.0.0.1 -p 55432 -q && break ;;
      kafka)    (exec 3<>/dev/tcp/127.0.0.1/9092) 2>/dev/null && break ;;
      opa)      curl -sf 127.0.0.1:8181/health >/dev/null && break ;;
      operaton) curl -s -o /dev/null -w '%{http_code}' 127.0.0.1:8180/engine-rest/version | grep -qE '200|401' && break ;;
    esac
    sleep 1
    [[ $i == 180 ]] && { echo "timeout waiting for $dep" >&2; exit 1; }
  done
done
