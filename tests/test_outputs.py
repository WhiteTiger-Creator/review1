"""Verifier for edgekiln-tcpfeat-anvil — run agent binary, compare goldens/invariants.

Probe lattice tokens retained here only: ingest, export.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cdnqual_refs

OUT = Path("/app/qualitycast")
WIRE = Path("/app/polbay/run_manifest.json")
POLICY = Path("/app/polbay/cdn_policy.json")
VF_CANDIDATES = (
    Path("/opt/verifier-fixtures"),
    Path(__file__).resolve().parent / "verifier-fixtures",
)


def locate_vf(name: str) -> Path:
    for root in VF_CANDIDATES:
        p = root / name
        if p.is_file() or p.is_dir():
            return p
    raise FileNotFoundError(name)


def run_forge(*, env: dict[str, str] | None = None, wire: Path = WIRE) -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = ["/app/bin/cdnqual", "run-forge", "--wire", str(wire)]
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=merged)
    assert proc.returncode == 0, f"run-forge failed: {proc.stderr}\n{proc.stdout}"


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_netyard_bout_tensors_match_sealed_jsonl() -> None:
    """Public yard bout tensors must match the sealed session_features.jsonl golden."""
    run_forge()
    got = (OUT / "session_features.jsonl").read_bytes()
    exp = locate_vf("public_session_features.jsonl").read_bytes()
    assert got == exp


def test_milliwight_vector_matches_sealed_bank() -> None:
    """Intercept-aware L2 milliwights on the public yard must match the weights golden."""
    run_forge()
    got = (OUT / "ridge_weights.json").read_bytes()
    exp = locate_vf("public_ridge_weights.json").read_bytes()
    assert got == exp


def test_quality_ledger_and_tensor_digest_seal() -> None:
    """Quality ledger and tensor digest for the public yard must be byte-stable goldens."""
    run_forge()
    ledger = read_json(OUT / "eval_ledger.json")
    digest = read_json(OUT / "feature_digest.json")
    exp_ledger = read_json(locate_vf("public_eval_ledger.json"))
    exp_digest = read_json(locate_vf("public_feature_digest.json"))
    assert ledger == exp_ledger
    assert digest == exp_digest
    assert digest["features_sha256"] == cdnqual_refs.reference_public_features_sha256()
    assert digest["weights_sha256"] == cdnqual_refs.reference_public_weights_sha256()
    assert digest["ledger_sha256"] == cdnqual_refs.reference_public_ledger_sha256()


def test_qualitycast_rerun_stable_bytes() -> None:
    """Identical absolute --wire invocations must reprint matching qualitycast bytes."""
    run_forge()
    snap = {p.name: p.read_bytes() for p in OUT.iterdir() if p.is_file()}
    run_forge()
    for name, data in snap.items():
        assert (OUT / name).read_bytes() == data


def test_duplex_stitch_counters_on_netyard() -> None:
    """Duplex-stitch contract: rexmit/OOO/overlap counters and gap trim must hold."""
    run_forge()
    rows = [
        json.loads(line)
        for line in (OUT / "session_features.jsonl").read_text().splitlines()
        if line.strip()
    ]
    by = {r["bout_id"]: r["x"] for r in rows}
    assert by["bout_rexmit"][2] >= 1
    assert by["bout_ooo"][3] >= 1
    assert by["bout_overlap"][4] >= 1
    assert by["bout_gap"][0] == 4
    assert by["bout_clean"][8] == 1


def test_ridge_lambda_seven_flips_w_milli() -> None:
    """Changing ridge_lambda in cdn_policy must change weights_sha256 (perturbation)."""
    run_forge()
    base = (OUT / "ridge_weights.json").read_bytes()
    refs = read_json(locate_vf("perturbation_refs.json"))
    assert base == locate_vf("public_ridge_weights.json").read_bytes()

    pol = json.loads(POLICY.read_text())
    pol["ridge_lambda"] = 7
    with tempfile.TemporaryDirectory() as td:
        tmp_root = Path(td)
        tmp_pol = tmp_root / "cdn_policy.json"
        tmp_wire = tmp_root / "run_manifest.json"
        tmp_out = tmp_root / "qualitycast"
        tmp_pol.write_text(json.dumps(pol))
        wire = json.loads(WIRE.read_text())
        wire["policy"] = str(tmp_pol)
        wire["out_dir"] = str(tmp_out)
        tmp_wire.write_text(json.dumps(wire))
        tmp_out.mkdir(parents=True)
        proc = subprocess.run(
            ["/app/bin/cdnqual", "run-forge", "--wire", str(tmp_wire)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        new_bytes = (tmp_out / "ridge_weights.json").read_bytes()
        assert new_bytes != base
        assert cdnqual_refs.reference_lambda7_weights_sha256() == refs["lambda7_weights_sha256"]
        assert new_bytes != locate_vf("public_ridge_weights.json").read_bytes()


def test_hz_bank_matches_sealed_goldens() -> None:
    """Sealed holdout yard via CDNQUAL_CAPTURE_ROOT must match hidden goldens and floors."""
    hidden_root = locate_vf("hidden")
    labels = locate_vf("hidden_labels.jsonl")
    # Explicit verifier-fixtures path for trap coverage.
    assert "verifier-fixtures" in str(hidden_root) or hidden_root.is_dir()
    run_forge(
        env={
            "CDNQUAL_CAPTURE_ROOT": str(hidden_root),
            "CDNQUAL_LABELS": str(labels),
        }
    )
    floors = read_json(locate_vf("holdout_floors.json"))
    got_feat = (OUT / "session_features.jsonl").read_bytes()
    exp_feat = locate_vf("hidden_session_features.jsonl").read_bytes()
    assert got_feat == exp_feat
    got_w = (OUT / "ridge_weights.json").read_bytes()
    exp_w = locate_vf("hidden_ridge_weights.json").read_bytes()
    assert got_w == exp_w
    ledger = read_json(OUT / "eval_ledger.json")
    exp_ledger = read_json(locate_vf("hidden_eval_ledger.json"))
    assert ledger == exp_ledger
    assert ledger["bout_count"] >= floors["min_bout_count"]
    assert ledger["accuracy_milli"] >= floors["min_accuracy_milli"]
    assert [p["bout_id"] for p in ledger["predictions"]] == floors["expected_bout_ids"]
    digest = read_json(OUT / "feature_digest.json")
    assert digest == read_json(locate_vf("hidden_feature_digest.json"))


def test_hz_digest_matches_cdnqual_refs() -> None:
    """Hidden bank feature digest must match sealed reference under /opt/verifier-fixtures."""
    hidden_root = Path("/opt/verifier-fixtures/hidden")
    labels = Path("/opt/verifier-fixtures/hidden_labels.jsonl")
    run_forge(
        env={
            "CDNQUAL_CAPTURE_ROOT": str(hidden_root),
            "CDNQUAL_LABELS": str(labels),
        }
    )
    digest = read_json(OUT / "feature_digest.json")
    assert digest["features_sha256"] == cdnqual_refs.reference_hidden_features_sha256()
    assert digest["bout_ids"] == cdnqual_refs.reference_hidden_bout_ids()


def test_forge_packages_omit_specter_graph() -> None:
    """Specter lure under /app/decoy must stay off the forge import graph."""
    roots = [
        Path("/app/cmd"),
        Path("/app/framestream"),
        Path("/app/duplexstitch"),
        Path("/app/tensorloom"),
        Path("/app/entropymilli"),
        Path("/app/l2anvil"),
        Path("/app/kilnemit"),
        Path("/app/captureload"),
        Path("/app/qualityemit"),
    ]
    for root in roots:
        for path in root.rglob("*.go"):
            text = path.read_text(encoding="utf-8")
            assert "cdnqual/decoy" not in text, f"decoy import in {path}"


def test_cdn_policy_lambda_echoed_in_artifacts() -> None:
    """Config-driven: ledger and weights lambda must mirror cdn_policy.json."""
    pol = json.loads(POLICY.read_text())
    run_forge()
    ledger = read_json(OUT / "eval_ledger.json")
    assert ledger["policy_lambda"] == pol["ridge_lambda"]
    weights = read_json(OUT / "ridge_weights.json")
    assert weights["lambda"] == pol["ridge_lambda"]


def test_ledger_checkpoint_snap_mirrors_emit() -> None:
    """Staging checkpoint snapshot must be byte-identical to the eval_ledger export."""
    run_forge()
    ledger = (OUT / "eval_ledger.json").read_bytes()
    snapshot = (OUT / "checkpoint" / "eval_ledger.snap.json").read_bytes()
    assert snapshot == ledger


def test_public_digest_equals_cdnqual_refs() -> None:
    """Public digest shas must equal sealed reference_* helpers (not recomputed solvers)."""
    run_forge()
    digest = read_json(OUT / "feature_digest.json")
    assert digest["features_sha256"] == cdnqual_refs.reference_public_features_sha256()
    assert digest["weights_sha256"] == cdnqual_refs.reference_public_weights_sha256()
    assert digest["ledger_sha256"] == cdnqual_refs.reference_public_ledger_sha256()


def test_public_payload_hash_equals_cdnqual_refs() -> None:
    """Public payload_hash must match the sealed reference hash."""
    run_forge()
    ledger = read_json(OUT / "eval_ledger.json")
    assert ledger["payload_hash"] == cdnqual_refs.reference_public_payload_hash()


def test_hz_payload_hash_equals_cdnqual_refs() -> None:
    """Hidden payload_hash must match the sealed reference under verifier-fixtures."""
    run_forge(
        env={
            "CDNQUAL_CAPTURE_ROOT": "/opt/verifier-fixtures/hidden",
            "CDNQUAL_LABELS": "/opt/verifier-fixtures/hidden_labels.jsonl",
        }
    )
    ledger = read_json(OUT / "eval_ledger.json")
    assert ledger["payload_hash"] == cdnqual_refs.reference_hidden_payload_hash()


def test_bout_tensor_width_is_twelve() -> None:
    """Every bout tensor must be length 12 per bout-tensor contract."""
    run_forge()
    for line in (OUT / "session_features.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        assert len(row["x"]) == 12


def test_milliwight_width_includes_intercept() -> None:
    """Ridge weights must include intercept column (dim 13)."""
    run_forge()
    weights = read_json(OUT / "ridge_weights.json")
    assert weights["dim"] == 13
    assert len(weights["w_milli"]) == 13


def test_bout_id_order_is_lexicographic() -> None:
    """Feature rows and predictions must be bout_id ascending."""
    run_forge()
    ids = [
        json.loads(line)["bout_id"]
        for line in (OUT / "session_features.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert ids == sorted(ids)
    ledger = read_json(OUT / "eval_ledger.json")
    pred_ids = [p["bout_id"] for p in ledger["predictions"]]
    assert pred_ids == sorted(pred_ids)


def test_prefer_newest_overlap_byte_count() -> None:
    """bout_overlap must show overlap_byte_count >= 1 under prefer-newest."""
    run_forge()
    rows = {
        json.loads(line)["bout_id"]: json.loads(line)["x"]
        for line in (OUT / "session_features.jsonl").read_text().splitlines()
        if line.strip()
    }
    assert rows["bout_overlap"][4] >= 1
    assert rows["bout_overlap"][0] == 6


def test_cdnqual_schema_identifiers() -> None:
    """Ledger and digest must carry cdnqual schema identifiers."""
    run_forge()
    assert read_json(OUT / "eval_ledger.json")["schema"] == "cdnqual.ledger.v1"
    assert read_json(OUT / "feature_digest.json")["schema"] == "cdnqual.digest.v1"


def test_rebuild_cdnqual_emits_executable() -> None:
    """Rebuild script must leave an executable /app/bin/cdnqual."""
    proc = subprocess.run(
        ["bash", "/app/scripts/rebuild-cdnqual.sh"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert Path("/app/bin/cdnqual").is_file()
