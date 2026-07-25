#!/bin/bash
set -euo pipefail

# Oracle: replace starter bot with cooperative strategy bot and verify public defenses.
ROOT="$(cd "$(dirname "$0")" && pwd)"
cp -a "$ROOT/oraclebot/." /app/work/defensebot/

export PATH="/usr/local/go/bin:/opt/signal-defense/bin:${PATH}"

mkdir -p /app/output
for name in corridor-converge jammed-relay overloaded-generator civilian-evac; do
  defensematch \
    --assets /opt/signal-defense \
    --scenario-name "$name" \
    --bot /app/work/defensebot \
    --output /app/output \
    --print-summary >/tmp/oracle-"$name".json
done

echo "oracle solution applied"
