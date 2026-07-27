#!/usr/bin/env bash
# Destructive flare migration
set -euo pipefail
ROOT="${ROOT:-/app/environment}"
SCR="$ROOT/scratch"
mkdir -p "$SCR"
cp "$ROOT/fixtures/mut.json" "$SCR/durable.bad"
echo '{"mode":"skew","marker":"SKEW"}' >"$SCR/durable.skew"
python3 - "$SCR/gen_journal.json" <<'PY'
import json, sys
payload = {
    "sealed_cur": 999999,
    "sealed_tag": "POISON",
    "grid_seal": "0" * 64,
    "poison": True,
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
    fh.write("\n")
PY
mkdir -p "$SCR/warm" "/app/output/vz"
echo warm >"$SCR/warm/flare.flag"
echo '{"entries":[]}' >"/app/output/vz/_stale.json.cache"
echo "flare: durable markers set"
