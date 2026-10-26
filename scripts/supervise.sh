#!/usr/bin/env bash
# Minimal restart-on-exit supervisor (stands in for a Kubernetes/Compose restart policy).
# Usage: scripts/supervise.sh <pidfile> <command...>. The crash/resume test kills the child with SIGKILL;
# the supervisor restarts it, and Operaton hands the locked task to the new worker after the lock expires.
pidfile=$1; shift
trap 'kill "$child" 2>/dev/null; exit 0' TERM INT
while true; do
  "$@" & child=$!; echo "$child" > "$pidfile"
  wait "$child"; echo "[supervise] $1 exited ($?) – restarting in 1s" >&2; sleep 1
done
