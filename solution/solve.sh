#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="/app/output/q7_state"

install -d /app/bin /app/output "$STATE"

make -C /app/environment clean all
test -x /app/bin/q7

cp "$ROOT_DIR/oracle/m4.c" "/app/environment/cast/m4.c"
cp "$ROOT_DIR/oracle/r2.c" "/app/environment/libm/r2.c"
cp "$ROOT_DIR/oracle/k9.c" "/app/environment/tile/k9.c"
cp "$ROOT_DIR/oracle/w1.c" "/app/environment/adv/w1.c"
cp "$ROOT_DIR/oracle/checkpoint.c" "/app/environment/r8/checkpoint.c"

make -C /app/environment clean all
test -x /app/bin/q7

rm -f /app/output/sensitivity_trace.json
rm -rf "$STATE"
mkdir -p "$STATE"

/app/bin/q7 --mode start \
  --state-dir "$STATE" \
  --model /app/environment/fixtures/stiff_coupled.json \
  --trace-out /app/output/sensitivity_trace.json \
  --profile nominal

/app/bin/q7 --mode seal \
  --state-dir "$STATE" \
  --trace-out /app/output/sensitivity_trace.json

START_DIGEST="$(python3 -c 'import json; print(json.load(open("/app/output/sensitivity_trace.json"))["repro_digest"])')"
export START_DIGEST

/app/bin/q7 --mode resume \
  --state-dir "$STATE" \
  --model /app/environment/fixtures/stiff_coupled.json \
  --trace-out /app/output/sensitivity_trace.json \
  --profile scaled

/app/bin/q7 --mode seal \
  --state-dir "$STATE" \
  --trace-out /app/output/sensitivity_trace.json

/app/bin/q7 --mode resume \
  --state-dir "$STATE" \
  --model /app/environment/fixtures/stiff_coupled.json \
  --trace-out /app/output/sensitivity_trace.json \
  --profile scaled

python3 - <<'PY'
import json
from pathlib import Path

trace = json.loads(Path("/app/output/sensitivity_trace.json").read_text())
assert trace["rows"]
assert len(trace["repro_digest"]) == 16
head = json.loads(Path("/app/output/q7_state/head.json").read_text())
assert int(head["generation"]) == 2
slots = [json.loads(Path(f"/app/output/q7_state/slot_{idx}.json").read_text()) for idx in range(2)]
newest = max((slot for slot in slots if slot.get("sealed")), key=lambda slot: slot.get("slot_generation", 0))
assert newest["slot_generation"] == 2
assert newest["lineage_seed"] > newest["bind_seed"] > 0.0
for row in trace["rows"]:
    assert "emit_lane" in row and len(row["emit_lane"]) == 4
    assert abs(row["reported"] - row["reference"]) / max(abs(row["reference"]), 1e-14) <= 1e-10
PY
