"""Hallwarden latch poly-OLS verifier — vault/forecast/emit seal + pass-chain.
PROBE_MARKERS: snapshot load emit trust persistence replay sequence idempotent
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from hwml_ref import (
    chain_digest,
    load_workbook,
    reference_fit_commit,
    reference_pass_chain_row,
    reference_pin,
    reference_plaque,
    reference_run,
    reference_seal,
    reference_trust,
    reference_witness_row,
    stage_fingerprint,
)

APP = Path("/app")
STATE = APP / "state"
PLAQUE = APP / "plaque"
WITNESS = STATE / "emit_witness.jsonl"
FIX = APP / "fixtures"
DRIVER = Path("/app/binx/hwml")


def wipe_outputs() -> None:
    if STATE.exists():
        shutil.rmtree(STATE)
    if PLAQUE.exists():
        shutil.rmtree(PLAQUE)
    STATE.mkdir(parents=True)
    PLAQUE.mkdir(parents=True)


def drive(*, workbook=None, traces=None, mode: str | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = "/app"
    if workbook is not None:
        env["HWML_WORKBOOK"] = str(workbook)
    else:
        env.pop("HWML_WORKBOOK", None)
    if traces is not None:
        env["HWML_TRACES"] = str(traces)
    else:
        env.pop("HWML_TRACES", None)
    cmd = [str(DRIVER)]
    if mode:
        cmd.append(mode)
    else:
        cmd.append("eval")
    return subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hwml9_feature_training_inference_eval_artifacts():
    """Full training/inference eval writes /app/state feature artifacts and plaque."""
    wipe_outputs()
    assert drive().returncode == 0
    assert Path("/app/state/design_matrix.json").is_file()
    assert Path("/app/state/design_vault.json").is_file()
    assert Path("/app/state/latch_pin.json").is_file()
    assert Path("/app/state/beta_hat.json").is_file()
    assert Path("/app/state/fit_commit.json").is_file()
    assert Path("/app/state/beta_latch_seal.json").is_file()
    assert Path("/app/state/forecast_tape.json").is_file()
    assert Path("/app/state/emit_trust.json").is_file()
    assert Path("/app/state/run_log.jsonl").is_file()
    assert Path("/app/state/pass_chain.jsonl").is_file()
    assert Path("/app/plaque/promotion_plaque.json").is_file()
    trust = json.loads((STATE / "emit_trust.json").read_text(encoding="utf-8"))
    assert trust["scheme"] == "hwml.trust/v1"
    assert len(trust["vault_digest"]) == 64
    assert len(trust["seal_digest"]) == 64


def test_hwml9_feature_design_matrix_agrees_refml():
    """Quadratic design columns agree with independent reference."""
    wipe_outputs()
    assert drive().returncode == 0
    exp = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")
    assert read_json(STATE / "design_matrix.json")["rows"] == exp["design"]["rows"]
    assert read_json(STATE / "design_matrix.json")["column_names"] == exp["design"]["column_names"]
    assert int(read_json(STATE / "design_matrix.json")["policy_epoch"]) == int(exp["workbook"]["policy_epoch"])


def test_hwml9_vault_mirrors_design_rows():
    """Vault rows mirror design_matrix rows after id sort."""
    wipe_outputs()
    assert drive().returncode == 0
    d = read_json(STATE / "design_matrix.json")
    v = read_json(STATE / "design_vault.json")
    assert v["scheme"] == "hwml.vault/v1"
    assert v["rows"] == d["rows"]
    assert v["column_names"] == d["column_names"]
    assert v["source_trace_count"] >= 1
    assert int(v["policy_epoch"]) == int(d["policy_epoch"])


def test_hwml9_vault_latch_pin_binds_on_disk_vault():
    """Attest scheme, digest, and row_count match the on-disk design vault."""
    wipe_outputs()
    assert drive().returncode == 0
    vault = read_json(STATE / "design_vault.json")
    latch_pin = read_json(STATE / "latch_pin.json")
    exp = reference_pin(vault, STATE / "design_vault.json")
    assert latch_pin["scheme"] == "hwml.pin/v1"
    assert latch_pin["vault_digest"] == exp["vault_digest"]
    assert latch_pin["vault_digest"] == sha(STATE / "design_vault.json")
    assert latch_pin["row_count"] == len(vault["rows"])
    assert int(latch_pin["pin_seq"]) >= 1
    assert int(latch_pin["policy_epoch"]) == int(vault["policy_epoch"])


def test_hwml9_beta_latch_seal_binds():
    """Beta-latch seal binds beta/pin/vault digests and policy_epoch."""
    wipe_outputs()
    assert drive().returncode == 0
    pin = read_json(STATE / "latch_pin.json")
    wb = load_workbook(FIX / "eval_workbook.json")
    got = read_json(STATE / "beta_latch_seal.json")
    want = reference_seal(wb, STATE / "design_vault.json", STATE / "latch_pin.json", STATE / "beta_hat.json", pin)
    assert got == want
    assert got["scheme"] == "hwml.seal/v1"


def test_hwml9_model_training_beta_agrees_refml():
    """Learning-cohort OLS beta_hat agrees with independent reference."""
    wipe_outputs()
    assert drive().returncode == 0
    exp = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")
    assert read_json(STATE / "beta_hat.json")["values"] == exp["beta"]["values"]
    assert len(read_json(STATE / "beta_hat.json")["values"]) == 7


def test_hwml9_inference_metric_mape_r2_agree_refml():
    """MAPE and R2 agree with independent forecast metrics."""
    wipe_outputs()
    assert drive().returncode == 0
    exp = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")
    got = read_json(STATE / "forecast_tape.json")
    assert got["mape"] == exp["forecast"]["mape"]
    assert got["r2"] == exp["forecast"]["r2"]
    assert got["metrics_pass"] is True


def test_hwml9_model_eval_promoted_on_default_bundle():
    """Default specimen bundle promotes under MAPE/R2 dual gate."""
    wipe_outputs()
    assert drive().returncode == 0
    assert read_json(STATE / "forecast_tape.json")["metrics_pass"] is True
    assert read_json(PLAQUE / "promotion_plaque.json")["promoted"] is True


def test_hwml9_reserved_ids_only():
    """Forecast rows are reserved cohort ids only."""
    wipe_outputs()
    assert drive().returncode == 0
    design = read_json(STATE / "design_matrix.json")
    forecast = read_json(STATE / "forecast_tape.json")
    reserved = {r["id"] for r in design["rows"] if r["cohort"] == "reserved"}
    assert {r["id"] for r in forecast["rows"]} == reserved


def test_hwml9_rows_sorted_by_id():
    """Design and vault rows are ascending by specimen id."""
    wipe_outputs()
    assert drive().returncode == 0
    for name in ("design_matrix.json", "design_vault.json"):
        ids = [r["id"] for r in read_json(STATE / name)["rows"]]
        assert ids == sorted(ids)


def test_hwml9_fit_commit_pins_vault():
    """Fit commit vault_digest and beta_digest bind on-disk bytes."""
    wipe_outputs()
    assert drive().returncode == 0
    c = read_json(STATE / "fit_commit.json")
    assert c["vault_digest"] == sha(STATE / "design_vault.json")
    assert c["beta_digest"] == sha(STATE / "beta_hat.json")
    exp = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")
    assert c["learning_ids"] == exp["learning_ids"]
    want = reference_fit_commit(
        exp["workbook"], STATE / "design_vault.json", STATE / "beta_hat.json", exp["learning_ids"]
    )
    assert c == want


def test_hwml9_emit_trust_binds_stage_digests():
    """Emit trust digests bind vault/pin/beta/commit/seal/forecast on-disk bytes."""
    wipe_outputs()
    assert drive().returncode == 0
    forecast = read_json(STATE / "forecast_tape.json")
    workbook = load_workbook(FIX / "eval_workbook.json")
    got = read_json(STATE / "emit_trust.json")
    want = reference_trust(
        forecast,
        workbook,
        STATE / "design_vault.json",
        STATE / "latch_pin.json",
        STATE / "beta_hat.json",
        STATE / "fit_commit.json",
        STATE / "beta_latch_seal.json",
        STATE / "forecast_tape.json",
    )
    assert got == want


def test_hwml9_plaque_digests_pin_including_trust():
    """Plaque digests bind on-disk state bytes including seal and emit trust."""
    wipe_outputs()
    assert drive().returncode == 0
    p = read_json(PLAQUE / "promotion_plaque.json")
    assert p["design_digest"] == sha(STATE / "design_matrix.json")
    assert p["beta_digest"] == sha(STATE / "beta_hat.json")
    assert p["forecast_digest"] == sha(STATE / "forecast_tape.json")
    assert p["vault_digest"] == sha(STATE / "design_vault.json")
    assert p["fit_commit_digest"] == sha(STATE / "fit_commit.json")
    assert p["pin_digest"] == sha(STATE / "latch_pin.json")
    assert p["seal_digest"] == sha(STATE / "beta_latch_seal.json")
    assert p["trust_digest"] == sha(STATE / "emit_trust.json")
    assert int(p["pin_seq"]) == int(read_json(STATE / "latch_pin.json")["pin_seq"])
    assert int(p["policy_epoch"]) == int(load_workbook(FIX / "eval_workbook.json")["policy_epoch"])


def test_hwml9_refml_plaque_agrees():
    """Independent plaque builder agrees with on-disk plaque."""
    wipe_outputs()
    assert drive().returncode == 0
    exp = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")
    want = reference_plaque(
        exp["forecast"],
        exp["workbook"],
        STATE / "design_matrix.json",
        STATE / "beta_hat.json",
        STATE / "forecast_tape.json",
        STATE / "design_vault.json",
        STATE / "fit_commit.json",
        STATE / "latch_pin.json",
        STATE / "beta_latch_seal.json",
        STATE / "emit_trust.json",
    )
    assert read_json(PLAQUE / "promotion_plaque.json") == want


def test_hwml9_identity_propagates():
    """Identity propagates from workbook across state and plaque."""
    wipe_outputs()
    assert drive().returncode == 0
    ident = load_workbook(FIX / "eval_workbook.json")["identity"]
    for path in (
        STATE / "design_matrix.json",
        STATE / "design_vault.json",
        STATE / "latch_pin.json",
        STATE / "beta_hat.json",
        STATE / "fit_commit.json",
        STATE / "beta_latch_seal.json",
        STATE / "forecast_tape.json",
        STATE / "emit_trust.json",
        PLAQUE / "promotion_plaque.json",
    ):
        assert read_json(path)["identity"] == ident


def test_hwml9_second_eval_byte_stable_pass_chain_grows():
    """Replay keeps stage bytes identical and appends pass_chain pass_index 2."""
    wipe_outputs()
    assert drive().returncode == 0
    a_vault = (STATE / "design_vault.json").read_bytes()
    a_latch_pin = (STATE / "latch_pin.json").read_bytes()
    a_seal = (STATE / "beta_latch_seal.json").read_bytes()
    a_trust = (STATE / "emit_trust.json").read_bytes()
    a_plaque = (PLAQUE / "promotion_plaque.json").read_bytes()
    gen = read_json(STATE / "latch_pin.json")["pin_seq"]
    first = [json.loads(line) for line in (STATE / "pass_chain.jsonl").read_text().splitlines() if line.strip()]
    assert len(first) == 1
    assert first[0]["pass_index"] == 1
    assert first[0]["prior_digest"] == ""
    want_fp = stage_fingerprint(
        STATE / "design_vault.json",
        STATE / "latch_pin.json",
        STATE / "beta_hat.json",
        STATE / "fit_commit.json",
        STATE / "beta_latch_seal.json",
        STATE / "forecast_tape.json",
        STATE / "emit_trust.json",
    )
    assert first[0]["stage_fingerprint"] == want_fp
    assert first[0]["chain_digest"] == chain_digest(
        "", want_fp, first[0]["vault_digest"], first[0]["seal_digest"], int(first[0]["pin_seq"]), 1
    )
    assert drive().returncode == 0
    assert (STATE / "design_vault.json").read_bytes() == a_vault
    assert (STATE / "latch_pin.json").read_bytes() == a_latch_pin
    assert (STATE / "beta_latch_seal.json").read_bytes() == a_seal
    assert (STATE / "emit_trust.json").read_bytes() == a_trust
    assert (PLAQUE / "promotion_plaque.json").read_bytes() == a_plaque
    assert read_json(STATE / "latch_pin.json")["pin_seq"] == gen
    lines = [json.loads(line) for line in (STATE / "pass_chain.jsonl").read_text().splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[1]["pass_index"] == 2
    assert lines[1]["prior_digest"] == lines[0]["chain_digest"]
    assert lines[1]["stage_fingerprint"] == want_fp
    assert lines[1]["chain_digest"] == chain_digest(
        lines[0]["chain_digest"], want_fp, lines[1]["vault_digest"], lines[1]["seal_digest"], int(lines[1]["pin_seq"]), 2
    )


def test_hwml9_run_log_stages():
    """Run log lists design/vault/latch_pin/beta/commit/seal/forecast/trust/plaque."""
    wipe_outputs()
    assert drive().returncode == 0
    rows = [json.loads(line) for line in (STATE / "run_log.jsonl").read_text().splitlines() if line.strip()]
    assert [r["stage"] for r in rows] == [
        "design", "vault", "latch_pin", "beta", "commit", "seal", "forecast", "trust", "plaque"
    ]


def test_hwml9_vault_only_writes_state_snapshot():
    """Vault mode writes matrix/vault/pin only — no beta, seal, trust, plaque, or pass_chain."""
    wipe_outputs()
    assert drive(mode="vault").returncode == 0
    assert (STATE / "design_matrix.json").is_file()
    assert (STATE / "design_vault.json").is_file()
    assert (STATE / "latch_pin.json").is_file()
    assert not (STATE / "beta_hat.json").exists()
    assert not (STATE / "beta_latch_seal.json").exists()
    assert not (STATE / "emit_trust.json").exists()
    assert not (STATE / "pass_chain.jsonl").exists()
    assert not (PLAQUE / "promotion_plaque.json").exists()


def test_hwml9_forecast_keeps_vault_when_traces_mutate():
    """Forecast-only after trace mutation must keep staged vault/latch_pin/seal/plaque."""
    wipe_outputs()
    assert drive().returncode == 0
    vault_bytes = (STATE / "design_vault.json").read_bytes()
    latch_pin_bytes = (STATE / "latch_pin.json").read_bytes()
    seal_bytes = (STATE / "beta_latch_seal.json").read_bytes()
    trust_bytes = (STATE / "emit_trust.json").read_bytes()
    plaque_bytes = (PLAQUE / "promotion_plaque.json").read_bytes()
    digest = read_json(STATE / "latch_pin.json")["vault_digest"]
    traces = FIX / "labeled_traces.jsonl"
    original = traces.read_text(encoding="utf-8")
    try:
        lines = original.splitlines()
        row = json.loads(lines[0])
        row["ticks"] = [9, 9, 9, 9, 9, 9, 9, 9]
        lines[0] = json.dumps(row)
        traces.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert drive(mode="forecast").returncode == 0
        assert (STATE / "design_vault.json").read_bytes() == vault_bytes
        assert (STATE / "latch_pin.json").read_bytes() == latch_pin_bytes
        assert (STATE / "beta_latch_seal.json").read_bytes() == seal_bytes
        assert (STATE / "emit_trust.json").read_bytes() == trust_bytes
        assert (PLAQUE / "promotion_plaque.json").read_bytes() == plaque_bytes
        assert read_json(PLAQUE / "promotion_plaque.json")["vault_digest"] == digest
    finally:
        traces.write_text(original, encoding="utf-8")


def test_hwml9_vault_then_forecast_matches_full_eval():
    """vault then forecast produces the same latch_pin digest and plaque as full eval."""
    wipe_outputs()
    assert drive().returncode == 0
    full_digest = read_json(STATE / "latch_pin.json")["vault_digest"]
    full_plaque = read_json(PLAQUE / "promotion_plaque.json")
    wipe_outputs()
    assert drive(mode="vault").returncode == 0
    assert (STATE / "design_vault.json").is_file()
    assert (STATE / "latch_pin.json").is_file()
    assert not (PLAQUE / "promotion_plaque.json").exists()
    assert drive(mode="forecast").returncode == 0
    assert read_json(STATE / "latch_pin.json")["vault_digest"] == full_digest
    got = read_json(PLAQUE / "promotion_plaque.json")
    assert got["promoted"] == full_plaque["promoted"]
    assert got["mape"] == full_plaque["mape"]
    assert got["r2"] == full_plaque["r2"]
    assert got["vault_digest"] == full_plaque["vault_digest"]
    assert got["pin_digest"] == full_plaque["pin_digest"]
    assert got["seal_digest"] == full_plaque["seal_digest"]
    assert got["trust_digest"] == full_plaque["trust_digest"]


def test_hwml9_mutated_vault_without_repin_breaks_forecast():
    """Forecast must fail when design_vault is mutated without refreshing latch_pin."""
    wipe_outputs()
    assert drive(mode="vault").returncode == 0
    vault = read_json(STATE / "design_vault.json")
    vault["rows"][0]["target_energy"] = float(vault["rows"][0]["target_energy"]) + 1.0
    (STATE / "design_vault.json").write_text(json.dumps(vault, indent=2) + "\n", encoding="utf-8")
    proc = drive(mode="forecast")
    assert proc.returncode != 0
    assert not (PLAQUE / "promotion_plaque.json").exists()


def test_hwml9_policy_epoch_drift_breaks_forecast():
    """Forecast must abort when staged vault policy_epoch drifts from the workbook."""
    wipe_outputs()
    assert drive(mode="vault").returncode == 0
    vault = read_json(STATE / "design_vault.json")
    vault["policy_epoch"] = int(vault["policy_epoch"]) + 9
    (STATE / "design_vault.json").write_text(json.dumps(vault, indent=2) + "\n", encoding="utf-8")
    # Refresh pin digest to match mutated vault so epoch check is the failure mode
    pin = read_json(STATE / "latch_pin.json")
    pin["vault_digest"] = sha(STATE / "design_vault.json")
    pin["policy_epoch"] = vault["policy_epoch"]
    (STATE / "latch_pin.json").write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    proc = drive(mode="forecast")
    assert proc.returncode != 0
    assert not (PLAQUE / "promotion_plaque.json").exists()


def test_hwml9_stale_trust_after_beta_mutation_breaks_emit():
    """Emit must fail when beta_hat mutates without refreshing emit_trust."""
    wipe_outputs()
    assert drive().returncode == 0
    prior_trust = (STATE / "emit_trust.json").read_text(encoding="utf-8")
    beta = read_json(STATE / "beta_hat.json")
    beta["values"] = [float(v) + 0.001 for v in beta["values"]]
    (STATE / "beta_hat.json").write_text(json.dumps(beta, indent=2) + "\n", encoding="utf-8")
    (PLAQUE / "promotion_plaque.json").unlink(missing_ok=True)
    proc = drive(mode="emit")
    assert proc.returncode != 0
    assert not (PLAQUE / "promotion_plaque.json").exists()
    assert (STATE / "emit_trust.json").read_text(encoding="utf-8") == prior_trust


def test_hwml9_stale_seal_after_beta_mutation_breaks_emit():
    """Emit must fail when beta mutates even if trust digests are forcibly refreshed without seal."""
    wipe_outputs()
    assert drive().returncode == 0
    beta = read_json(STATE / "beta_hat.json")
    beta["values"] = [float(v) + 0.002 for v in beta["values"]]
    (STATE / "beta_hat.json").write_text(json.dumps(beta, indent=2) + "\n", encoding="utf-8")
    trust = read_json(STATE / "emit_trust.json")
    trust["beta_digest"] = sha(STATE / "beta_hat.json")
    (STATE / "emit_trust.json").write_text(json.dumps(trust, indent=2) + "\n", encoding="utf-8")
    (PLAQUE / "promotion_plaque.json").unlink(missing_ok=True)
    proc = drive(mode="emit")
    assert proc.returncode != 0
    assert not (PLAQUE / "promotion_plaque.json").exists()


def test_hwml9_stale_trust_after_forecast_mutation_breaks_emit():
    """Emit must fail when forecast_tape mutates without refreshing emit_trust."""
    wipe_outputs()
    assert drive().returncode == 0
    prior_trust = json.loads((STATE / "emit_trust.json").read_text(encoding="utf-8"))
    tape = read_json(STATE / "forecast_tape.json")
    tape["mape"] = float(tape["mape"]) + 0.01
    (STATE / "forecast_tape.json").write_text(json.dumps(tape, indent=2) + "\n", encoding="utf-8")
    (PLAQUE / "promotion_plaque.json").unlink(missing_ok=True)
    proc = drive(mode="emit")
    assert proc.returncode != 0
    assert not (PLAQUE / "promotion_plaque.json").exists()
    assert prior_trust["forecast_digest"] != sha(STATE / "forecast_tape.json")


def test_hwml9_emit_rewrites_plaque_when_trust_fresh():
    """Emit succeeds and rewrites plaque digests when trust+seal still match files."""
    wipe_outputs()
    assert drive().returncode == 0
    trust_digest = sha(STATE / "emit_trust.json")
    seal_digest = sha(STATE / "beta_latch_seal.json")
    chain_before = (STATE / "pass_chain.jsonl").read_text(encoding="utf-8")
    (PLAQUE / "promotion_plaque.json").unlink()
    assert drive(mode="emit").returncode == 0
    p = read_json(PLAQUE / "promotion_plaque.json")
    assert p["trust_digest"] == trust_digest
    assert p["seal_digest"] == seal_digest
    assert p["promoted"] is True
    assert (STATE / "pass_chain.jsonl").read_text(encoding="utf-8") == chain_before


def test_hwml9_sidecut_not_imported():
    """latchml must not import sidecut or decoy."""
    for p in (APP / "latchml").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "sidecut" not in text
        assert "decoy" not in text


def test_hwml9_decoy_ridge_off_hot_path():
    """Decoy ridge module exists but is not imported by latchml."""
    assert (APP / "decoy" / "ridge_always.py").is_file()
    blob = " ".join(p.read_text(encoding="utf-8") for p in (APP / "latchml").glob("*.py"))
    assert "ridge_always" not in blob


def test_hwml9_scoregate_miss_blocks():
    """Noisy reserved targets block promotion."""
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "metric-miss"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    assert read_json(PLAQUE / "promotion_plaque.json")["promoted"] is False


def test_hwml9_mape_trap_fails_mape_only():
    """mape_trap fixture fails MAPE ceiling while R2 still clears the floor."""
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "mape-trap"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    tape = read_json(STATE / "forecast_tape.json")
    card = read_json(PLAQUE / "promotion_plaque.json")
    assert float(tape["r2"]) >= float(tape["r2_floor"])
    assert float(tape["mape"]) > float(tape["mape_ceiling"])
    assert card["promoted"] is False


def test_hwml9_r2_trap_fails_r2_only():
    """r2_trap fixture fails R2 floor while MAPE still clears the ceiling."""
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "r2-trap"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    tape = read_json(STATE / "forecast_tape.json")
    card = read_json(PLAQUE / "promotion_plaque.json")
    assert float(tape["mape"]) <= float(tape["mape_ceiling"])
    assert float(tape["r2"]) < float(tape["r2_floor"])
    assert card["promoted"] is False


def test_hwml9_specimen_spike_alters_mape():
    """Spiked reserved ticks change MAPE vs baseline."""
    base = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")["forecast"]["mape"]
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "feature-spike"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    assert read_json(STATE / "forecast_tape.json")["mape"] != base


def test_hwml9_no_reserved_blocks():
    """No reserved cohort cannot promote."""
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "no-holdout"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    assert read_json(STATE / "forecast_tape.json")["rows"] == []
    assert read_json(PLAQUE / "promotion_plaque.json")["promoted"] is False


def test_hwml9_ridge_bait_ignored():
    """Workbook ridge_lambda bait must not change plain OLS beta."""
    base = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")["beta"]["values"]
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "ridge-bait"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    assert read_json(STATE / "beta_hat.json")["values"] == base


def test_hwml9_shuffled_input_still_sorted():
    """Shuffled learning file order still yields id-sorted design rows and matching beta."""
    base = reference_run(FIX / "eval_workbook.json", FIX / "labeled_traces.jsonl")
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "shuffled-ids"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    ids = [r["id"] for r in read_json(STATE / "design_vault.json")["rows"]]
    assert ids == sorted(ids)
    assert read_json(STATE / "beta_hat.json")["values"] == base["beta"]["values"]


def test_hwml9_miss_digests_still_pin():
    """Failed promotion still binds digests including vault, latch_pin, seal, and emit_trust."""
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "metric-miss"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    p = read_json(PLAQUE / "promotion_plaque.json")
    assert p["design_digest"] == sha(STATE / "design_matrix.json")
    assert p["vault_digest"] == sha(STATE / "design_vault.json")
    assert p["pin_digest"] == sha(STATE / "latch_pin.json")
    assert p["seal_digest"] == sha(STATE / "beta_latch_seal.json")
    assert p["trust_digest"] == sha(STATE / "emit_trust.json")
    assert read_json(STATE / "emit_trust.json")["metrics_pass"] is False


def test_hwml9_quadratic_columns_present():
    """Design column_names include squared terms."""
    wipe_outputs()
    assert drive().returncode == 0
    names = read_json(STATE / "design_matrix.json")["column_names"]
    assert "mean_sq" in names and "max_sq" in names and "std_sq" in names


def test_hwml9_predictions_finite():
    """Forecast predictions are finite."""
    wipe_outputs()
    assert drive().returncode == 0
    for row in read_json(STATE / "forecast_tape.json")["rows"]:
        assert row["prediction"] == row["prediction"]


def read_json_lines(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_witness_lines():
    return read_json_lines(WITNESS)


def test_hwml9_emit_appends_witness_row_agrees_refml():
    """Successful emit appends an emit_witness line agreeing with the independent builder."""
    wipe_outputs()
    assert drive().returncode == 0
    assert not WITNESS.exists()
    assert drive(mode="emit").returncode == 0
    lines = read_witness_lines()
    assert len(lines) == 1
    pin = read_json(STATE / "latch_pin.json")
    want = reference_witness_row(
        "",
        PLAQUE / "promotion_plaque.json",
        STATE / "emit_trust.json",
        STATE / "beta_latch_seal.json",
        int(pin["pin_seq"]),
        1,
    )
    assert lines[0] == want
    assert lines[0]["plaque_digest"] == sha(PLAQUE / "promotion_plaque.json")


def test_hwml9_second_emit_witness_chain_grows_byte_stable():
    """Repeated emit keeps plaque bytes fixed while emit_witness grows and links."""
    wipe_outputs()
    assert drive().returncode == 0
    chain_before = (STATE / "pass_chain.jsonl").read_text(encoding="utf-8")
    assert drive(mode="emit").returncode == 0
    plaque_bytes = (PLAQUE / "promotion_plaque.json").read_bytes()
    assert drive(mode="emit").returncode == 0
    assert (PLAQUE / "promotion_plaque.json").read_bytes() == plaque_bytes
    lines = read_witness_lines()
    assert len(lines) == 2
    assert lines[1]["witness_index"] == 2
    assert lines[1]["prior_digest"] == lines[0]["witness_digest"]
    pin = read_json(STATE / "latch_pin.json")
    want = reference_witness_row(
        lines[0]["witness_digest"],
        PLAQUE / "promotion_plaque.json",
        STATE / "emit_trust.json",
        STATE / "beta_latch_seal.json",
        int(pin["pin_seq"]),
        2,
    )
    assert lines[1] == want
    assert (STATE / "pass_chain.jsonl").read_text(encoding="utf-8") == chain_before


def test_hwml9_forecast_never_writes_witness():
    """Forecast/eval passes must not create or grow the emit witness ledger."""
    wipe_outputs()
    assert drive().returncode == 0
    assert not WITNESS.exists()
    assert drive().returncode == 0
    assert not WITNESS.exists()
    assert drive(mode="emit").returncode == 0
    assert len(read_witness_lines()) == 1
    assert drive().returncode == 0
    assert len(read_witness_lines()) == 1


def test_hwml9_failed_emit_appends_no_witness():
    """Aborted emit after beta mutation leaves the witness ledger untouched."""
    wipe_outputs()
    assert drive().returncode == 0
    assert drive(mode="emit").returncode == 0
    witness_bytes = WITNESS.read_bytes()
    beta = read_json(STATE / "beta_hat.json")
    beta["values"] = [float(v) + 0.003 for v in beta["values"]]
    (STATE / "beta_hat.json").write_text(json.dumps(beta, indent=2) + "\n", encoding="utf-8")
    assert drive(mode="emit").returncode != 0
    assert WITNESS.read_bytes() == witness_bytes


def test_hwml9_emit_without_forecast_state_fails():
    """Emit with only a staged vault must exit non-zero without plaque or witness."""
    wipe_outputs()
    assert drive(mode="vault").returncode == 0
    assert drive(mode="emit").returncode != 0
    assert not (PLAQUE / "promotion_plaque.json").exists()
    assert not WITNESS.exists()


def test_hwml9_pin_rotation_across_vault_refresh():
    """pin_seq rotates 1 -> 2 -> 3 across vault byte changes; return to old bytes never reuses old seq."""
    wipe_outputs()
    assert drive().returncode == 0
    first_digest = read_json(STATE / "latch_pin.json")["vault_digest"]
    assert int(read_json(STATE / "latch_pin.json")["pin_seq"]) == 1
    chain1 = read_json_lines(STATE / "pass_chain.jsonl")
    traces = FIX / "labeled_traces.jsonl"
    original = traces.read_text(encoding="utf-8")
    try:
        lines = original.splitlines()
        row = json.loads(lines[0])
        row["target_energy"] = float(row["target_energy"]) + 5.0
        lines[0] = json.dumps(row)
        traces.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert drive().returncode == 0
        pin2 = read_json(STATE / "latch_pin.json")
        assert int(pin2["pin_seq"]) == 2
        assert pin2["vault_digest"] != first_digest
        chain2 = read_json_lines(STATE / "pass_chain.jsonl")
        assert len(chain2) == 2
        assert chain2[1]["prior_digest"] == chain1[0]["chain_digest"]
        assert chain2[1]["stage_fingerprint"] != chain1[0]["stage_fingerprint"]
        assert int(read_json(PLAQUE / "promotion_plaque.json")["pin_seq"]) == 2
    finally:
        traces.write_text(original, encoding="utf-8")
    assert drive().returncode == 0
    pin3 = read_json(STATE / "latch_pin.json")
    assert int(pin3["pin_seq"]) == 3
    assert pin3["vault_digest"] == first_digest
    chain3 = read_json_lines(STATE / "pass_chain.jsonl")
    assert len(chain3) == 3
    assert chain3[2]["prior_digest"] == chain3[1]["chain_digest"]
    assert int(chain3[2]["pin_seq"]) == 3
    assert int(read_json(PLAQUE / "promotion_plaque.json")["pin_seq"]) == 3


def test_hwml9_trunc_shift_agrees_refml():
    """trunc_decimals=3 workbook re-truncates every stage and still promotes."""
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "trunc-shift"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    exp = reference_run(root / "eval_workbook.json", root / "labeled_traces.jsonl")
    assert read_json(STATE / "design_matrix.json")["rows"] == exp["design"]["rows"]
    assert read_json(STATE / "beta_hat.json")["values"] == exp["beta"]["values"]
    tape = read_json(STATE / "forecast_tape.json")
    assert tape["mape"] == exp["forecast"]["mape"]
    assert tape["r2"] == exp["forecast"]["r2"]
    plaque = read_json(PLAQUE / "promotion_plaque.json")
    assert plaque["promoted"] == exp["forecast"]["metrics_pass"]
    assert int(plaque["policy_epoch"]) == int(exp["workbook"]["policy_epoch"])


def test_hwml9_negative_energy_tape_agrees_refml():
    """Mixed-sign targets keep abs_pct/MAPE math on the documented absolute-value guard."""
    wipe_outputs()
    root = Path("/opt/verifier-fixtures") / "negative-energy"
    assert drive(workbook=root / "eval_workbook.json", traces=root / "labeled_traces.jsonl").returncode == 0
    exp = reference_run(root / "eval_workbook.json", root / "labeled_traces.jsonl")
    tape = read_json(STATE / "forecast_tape.json")
    assert tape["rows"] == exp["forecast"]["rows"]
    assert tape["mape"] == exp["forecast"]["mape"]
    assert tape["r2"] == exp["forecast"]["r2"]
    assert tape["metrics_pass"] is False
    assert any(float(r["target_energy"]) < 0 for r in tape["rows"])
    assert read_json(PLAQUE / "promotion_plaque.json")["promoted"] is False


def test_hwml9_pass_chain_row_agrees_refml():
    """First pass_chain line agrees with independent chain builder."""
    wipe_outputs()
    assert drive().returncode == 0
    pin = read_json(STATE / "latch_pin.json")
    row = next(
        json.loads(line)
        for line in (STATE / "pass_chain.jsonl").read_text().splitlines()
        if line.strip()
    )
    want = reference_pass_chain_row(
        "",
        STATE / "design_vault.json",
        STATE / "latch_pin.json",
        STATE / "beta_hat.json",
        STATE / "fit_commit.json",
        STATE / "beta_latch_seal.json",
        STATE / "forecast_tape.json",
        STATE / "emit_trust.json",
        pin["pin_seq"],
        1,
    )
    assert row == want
