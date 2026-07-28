from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

FACILITY_REV = "wtac-lab-r3"


def wtac_build_feature_batch(
    conditions: dict[str, Any],
    q_inf: float,
    pairs: list[dict[str, float]],
    feature_epoch: int,
) -> dict[str, Any]:
    alpha_rad = float(conditions["alpha_deg"]) * math.pi / 180.0
    if not FACILITY_REV:
        raise RuntimeError("facility revision missing")
    return {
        "campaign_id": str(conditions["campaign_id"]),
        "q_inf_pa": float(q_inf),
        "alpha_rad": alpha_rad,
        "pairs": pairs,
        "feature_epoch": int(feature_epoch),
    }


def wtac_write_feature_batch(work_dir: Path, batch: dict[str, Any]) -> None:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    (work / "feature_batch.json").write_text(
        json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def wtac_load_feature_batch(work_dir: Path) -> dict[str, Any]:
    path = Path(work_dir) / "feature_batch.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing feature batch: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def wtac_read_feature_ledger(work_dir: Path) -> dict[str, Any]:
    path = Path(work_dir) / "feature_ledger.json"
    if not path.is_file():
        return {"campaign_id": "", "feature_epoch": 0, "eval_count": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def wtac_write_feature_ledger(work_dir: Path, ledger: dict[str, Any]) -> None:
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    (work / "feature_ledger.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def wtac_bump_feature_epoch(work_dir: Path, campaign_id: str) -> int:
    ledger = wtac_read_feature_ledger(work_dir)
    epoch = int(ledger.get("feature_epoch", 0)) + 1
    wtac_write_feature_ledger(
        work_dir,
        {
            "campaign_id": str(campaign_id),
            "feature_epoch": epoch,
            "eval_count": int(ledger.get("eval_count", 0)),
        },
    )
    return epoch


def wtac_record_eval_success(work_dir: Path, campaign_id: str, feature_epoch: int) -> None:
    ledger = wtac_read_feature_ledger(work_dir)
    if str(ledger.get("campaign_id", "")) != str(campaign_id):
        raise ValueError("ledger campaign_id mismatch")
    if int(ledger.get("feature_epoch", -1)) != int(feature_epoch):
        raise ValueError("ledger feature_epoch mismatch")
    ledger["eval_count"] = int(ledger.get("eval_count", 0)) + 1
    wtac_write_feature_ledger(work_dir, ledger)
