# fyop-atlas CLI

Drive the occupancy-dynamics path-integral simulation with /app/bin/fyop-atlas.

## Commands

- `fyop-atlas ingest` — bind observations from /app/yard-alpha (or HFSY_YARD_DIR) into /app/state/yard-staging.json and /app/state/ingest-snapshot.json
- `fyop-atlas optimize` — solve the discrete occupancy-dynamics trajectory from the staged snapshot only; write /app/state/shunting-validated.json
- `fyop-atlas export` — publish sealed path-integral atlas metrics from validated state only into /app/output/shunting-sequence.json plus /app/state/export-manifest.json and /app/state/export-ledger.json

Rebuild the launcher after source edits:

```bash
bash /app/scripts/build.sh
```

PYTHONPATH includes /app so `python3 -m fyop` resolves the package under /app/fyop.
