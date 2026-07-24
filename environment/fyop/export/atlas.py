"""Export stage: read validated, write shunting-sequence.json, export-manifest, export-ledger."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from fyop.staging.jsonutil import pretty, sha256hex
from fyop.staging.ingest import read_validated


def export(state_dir: Path, output_dir: Path) -> None:
    """Read shunting-validated.json and produce sequence, manifest, and ledger."""
    state_dir = Path(state_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    validated = read_validated(state_dir)

    sequence = {
        "train_id": validated["train_id"],
        "commands": validated["commands"],
        "total_distance_m": validated["total_distance_m"],
        "outbound_blocks": validated["outbound_blocks"],
        "loco_end_track": validated["loco_end_track"],
    }
    sequence_content = pretty(sequence)
    (output_dir / "shunting-sequence.json").write_text(sequence_content)

    fingerprint = sha256hex(sequence_content)

    manifest = {
        "train_id": validated["train_id"],
        "staging_hash": validated["staging_hash"],
        "export_fingerprint": fingerprint,
        "command_count": len(validated["commands"]),
        "total_distance_m": validated["total_distance_m"],
    }
    (state_dir / "export-manifest.json").write_text(pretty(manifest))

    _update_ledger(state_dir, validated["staging_hash"], fingerprint)


def _update_ledger(state_dir: Path, staging_hash: str, export_fingerprint: str) -> None:
    """Append an entry to the cumulative export-ledger.json."""
    ledger_path = state_dir / "export-ledger.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text())
        exports = ledger.get("exports", [])
    else:
        ledger = {}
        exports = []

    exports.append({
        "staging_hash": staging_hash,
        "export_fingerprint": export_fingerprint,
        "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    ledger["exports"] = exports
    ledger_path.write_text(pretty(ledger))
