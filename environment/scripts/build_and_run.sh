#!/bin/bash
set -euo pipefail

cd /app
rm -rf /app/build
mkdir -p /app/build /app/output
javac -d /app/build $(find /app/environment/core /app/environment/flow /app/environment/reduce -name '*.java' -print | sort)
rm -f /app/output/field_report.json
if [ "${1:-}" = "--alternate" ]; then
  java -cp /app/build terrain.Main --alternate
else
  java -cp /app/build terrain.Main
fi
