"""Behavioral checks for curriculum cohort WAL resume and eval fence."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/app/environment/scripts")
from ref_kit import expected_trace, fence_hex, load_pol, load_seeds, sha16

APP = Path("/app")
PACKS = APP / "packs"
OUT = APP / "output" / "cohort_trace.json"
STATE = APP / "output" / "cohort_state"


def _drive_session(packs: Path = PACKS, out: Path = OUT, state: Path = STATE) -> dict:
    subprocess.run(
        ["/app/environment/scripts/build_cqrun.sh"],
        check=True,
        cwd="/app",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    if state.exists():
        shutil.rmtree(state)
    subprocess.run(
        [
            "/app/bin/cqrun",
            "run",
            "--packs",
            str(packs),
            "--out",
            str(out),
            "--state",
            str(state),
        ],
        check=True,
        cwd="/app",
    )
    assert out.is_file(), "cohort_trace.json missing after run"
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def trace() -> dict:
    return _drive_session()


@pytest.fixture(scope="module")
def expect() -> dict:
    return expected_trace()


def test_cq_schema_stamp(trace: dict, expect: dict) -> None:
    """Regenerated trace carries the public schema and row count."""
    assert set(trace) >= {"rows", "summary"}
    rows = trace["rows"]
    assert isinstance(rows, list) and len(rows) > 0
    assert set(rows[0]) >= {
        "scenario_id",
        "epoch",
        "item_id",
        "band",
        "role",
        "admit_hex",
        "fence_hex",
        "weight",
    }
    summary = trace["summary"]
    assert set(summary) >= {
        "epochs",
        "rows_total",
        "cohort_digest",
        "resume_digest",
        "fence_status",
        "wal_depth",
    }
    assert summary["rows_total"] == len(rows) == expect["summary"]["rows_total"]
    assert summary["epochs"] == expect["summary"]["epochs"] == 2


def test_cq_admit_fold(trace: dict, expect: dict) -> None:
    """cohort_digest matches sorted admit_hex derivation after coherent selection."""
    hexes = sorted(r["admit_hex"] for r in trace["rows"])
    assert trace["summary"]["cohort_digest"] == sha16(",".join(hexes))
    assert trace["summary"]["cohort_digest"] == expect["summary"]["cohort_digest"]
    by_key = {(r["scenario_id"], r["epoch"], r["item_id"], r["role"]): r for r in trace["rows"]}
    matched = 0
    for er in expect["rows"]:
        got = by_key[(er["scenario_id"], er["epoch"], er["item_id"], er["role"])]
        assert (got["band"], got["admit_hex"], got["fence_hex"]) == (
            er["band"],
            er["admit_hex"],
            er["fence_hex"],
        )
        matched += 1
    assert matched == len(expect["rows"]) == len(trace["rows"])


def test_cq_fence_window(trace: dict, expect: dict) -> None:
    """Eval fence stays sealed across the lag window after interrupt."""
    assert trace["summary"]["fence_status"] == "sealed"
    assert expect["summary"]["fence_status"] == "sealed"
    pol = load_pol()
    fence_lag = int(pol["fence_lag"])
    train_by_epoch: dict[int, set[tuple[str, str]]] = {}
    for r in trace["rows"]:
        if r["role"] == "train":
            e = int(r["epoch"])
            bucket = train_by_epoch.get(e)
            if bucket is None:
                bucket = set()
                train_by_epoch[e] = bucket
            bucket.add((r["scenario_id"], r["item_id"]))
    for r in trace["rows"]:
        bit = 0
        if r["role"] == "eval":
            e = int(r["epoch"])
            forbidden: set[tuple[str, str]] = set()
            for k in range(e - fence_lag, e):
                forbidden |= train_by_epoch.get(k, set())
            if (r["scenario_id"], r["item_id"]) in forbidden:
                bit = 1
        assert r["fence_hex"] == fence_hex(r["admit_hex"], bit)
        assert bit == 0


def test_cq_replay_stamp(trace: dict, expect: dict) -> None:
    """resume_digest reflects WAL-replayed competence, not a stale snap blob."""
    assert trace["summary"]["resume_digest"] == expect["summary"]["resume_digest"]
    assert trace["summary"]["wal_depth"] == expect["summary"]["wal_depth"]
    assert trace["summary"]["wal_depth"] == len(trace["rows"])


def test_cq_second_pass(trace: dict) -> None:
    """Second full harness run rewrites identical field values."""
    first = json.dumps(trace, sort_keys=True)
    second = _drive_session()
    assert json.dumps(second, sort_keys=True) == first
    assert second["summary"]["fence_status"] == "sealed"


def test_cq_pack_shuffle(tmp_path: Path, expect: dict) -> None:
    """Reversing item order inside packs does not change coherent digests."""
    packs = tmp_path
    for src in sorted(PACKS.glob("seed_*.json")):
        data = json.loads(src.read_text(encoding="utf-8"))
        data["items"] = list(reversed(data["items"]))
        (packs / src.name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    out = tmp_path / "out.json"
    state = tmp_path / "state"
    got = _drive_session(packs=packs, out=out, state=state)
    assert got["summary"]["cohort_digest"] == expect["summary"]["cohort_digest"]
    assert got["summary"]["resume_digest"] == expect["summary"]["resume_digest"]
    assert got["summary"]["fence_status"] == "sealed"


def test_cq_lag_holdout(trace: dict, expect: dict) -> None:
    """Epoch-2 eval cohorts stay outside the epoch-1 train set (delayed fence)."""
    e1_train = {
        (r["scenario_id"], r["item_id"])
        for r in trace["rows"]
        if r["role"] == "train" and int(r["epoch"]) == 1
    }
    e2_eval = [
        r for r in trace["rows"] if r["role"] == "eval" and int(r["epoch"]) == 2
    ]
    assert e2_eval
    for r in e2_eval:
        assert (r["scenario_id"], r["item_id"]) not in e1_train
    exp_e2 = {
        (r["scenario_id"], r["item_id"])
        for r in expect["rows"]
        if r["role"] == "eval" and int(r["epoch"]) == 2
    }
    got_e2 = {(r["scenario_id"], r["item_id"]) for r in e2_eval}
    assert got_e2 == exp_e2


def test_cq_ema_step(trace: dict) -> None:
    """Train rows advance competence by the public EMA; eval rows do not."""
    pol = load_pol()
    alpha = float(pol["alpha"])
    decimals = int(pol["weight_decimals"])
    seeds = {s["id"]: {it["item_id"]: it for it in s["items"]} for s in load_seeds()}
    weights: dict[tuple[str, str], float] = {}
    for sid, items in seeds.items():
        for iid, it in items.items():
            weights[(sid, iid)] = float(it["prior"])
    for r in trace["rows"]:
        key = (r["scenario_id"], r["item_id"])
        assert f"{float(r['weight']):.{decimals}f}" == f"{weights[key]:.{decimals}f}"
        if r["role"] == "train":
            s = float(seeds[r["scenario_id"]][r["item_id"]]["signal"])
            weights[key] = (1.0 - alpha) * weights[key] + alpha * s


def test_cq_stale_wipe(expect: dict) -> None:
    """Stale hand-written JSON is cleared; only a rebuilt harness run counts."""
    OUT.write_text(
        json.dumps({"rows": [], "summary": {"fence_status": "sealed"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    got = _drive_session()
    assert got["summary"]["rows_total"] == expect["summary"]["rows_total"]
    assert got["summary"]["cohort_digest"] == expect["summary"]["cohort_digest"]
    assert got["summary"]["resume_digest"] == expect["summary"]["resume_digest"]
    assert got["summary"]["fence_status"] == "sealed"
    assert got["summary"]["wal_depth"] == expect["summary"]["wal_depth"]
    assert len(got["rows"]) == expect["summary"]["rows_total"]
    assert all(r["role"] in {"train", "eval"} for r in got["rows"])
    assert all(int(r["epoch"]) in {1, 2} for r in got["rows"])
    assert {r["scenario_id"] for r in got["rows"]} == {s["id"] for s in load_seeds()}
