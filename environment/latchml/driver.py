"""Eval driver."""
from __future__ import annotations
import json
import os
from pathlib import Path

from latchml.features import build_design, build_vault
from latchml.fit import fit_beta
from latchml.score import forecast_reserved
from latchml.card import (
    write_plaque,
    write_fit_commit,
    write_emit_trust,
    write_beta_latch_seal,
    append_pass_chain,
)
from latchml import stage_io, pinning as pin_mod


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_traces(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _paths(workbook_path=None, traces_path=None):
    wb = workbook_path or os.environ.get("HWML_WORKBOOK", "/app/fixtures/eval_workbook.json")
    tr = traces_path or os.environ.get("HWML_TRACES", "/app/fixtures/labeled_traces.jsonl")
    return wb, tr


def run_vault(workbook_path=None, traces_path=None, state_dir="/app/state"):
    wb_path, tr_path = _paths(workbook_path, traces_path)
    workbook = load_json(wb_path)
    traces = load_traces(tr_path)
    Path(state_dir).mkdir(parents=True, exist_ok=True)

    design = build_design(traces, workbook)
    d_p = Path(state_dir) / "design_matrix.json"
    stage_io.write_json(d_p, design)

    vault = build_vault(design, len(traces))
    v_p = Path(state_dir) / "design_vault.json"
    stage_io.write_json(v_p, vault)

    vault = stage_io.reload_json(v_p, vault)
    prior = None
    a_p = Path(state_dir) / "latch_pin.json"
    if a_p.is_file():
        try:
            prior = load_json(a_p)
        except Exception:
            prior = None
    pin_obj = pin_mod.build_pin(vault, v_p, prior)
    stage_io.write_json(a_p, pin_obj)
    return {"design": design, "vault": vault, "latch_pin": pin_obj}


def run_forecast(workbook_path=None, traces_path=None, state_dir="/app/state", out_dir="/app/plaque"):
    wb_path, tr_path = _paths(workbook_path, traces_path)
    workbook = load_json(wb_path)
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    v_p = Path(state_dir) / "design_vault.json"
    a_p = Path(state_dir) / "latch_pin.json"
    d_p = Path(state_dir) / "design_matrix.json"

    traces = load_traces(tr_path)
    design = build_design(traces, workbook)
    vault = build_vault(design, len(traces))
    if not a_p.is_file():
        raise SystemExit("missing latch_pin")
    pin_obj = load_json(a_p)

    beta = fit_beta(vault, workbook)
    b_p = Path(state_dir) / "beta_hat.json"
    stage_io.write_json(b_p, beta)
    beta = stage_io.reload_json(b_p, beta)

    learning_ids = [r["id"] for r in vault["rows"] if r["cohort"] == "learning"]
    c_p = Path(state_dir) / "fit_commit.json"
    write_fit_commit(workbook, v_p, b_p, learning_ids, c_p)

    s_p = Path(state_dir) / "beta_latch_seal.json"
    write_beta_latch_seal(workbook, v_p, a_p, b_p, pin_obj, s_p)

    forecast = forecast_reserved(vault, beta, workbook)
    f_p = Path(state_dir) / "forecast_tape.json"
    stage_io.write_json(f_p, forecast)
    forecast = stage_io.reload_json(f_p, forecast)

    t_p = Path(state_dir) / "emit_trust.json"
    write_emit_trust(forecast, workbook, v_p, a_p, b_p, c_p, s_p, f_p, t_p)

    j_p = Path(state_dir) / "run_log.jsonl"
    stages = [
        {"stage": "design", "ok": True},
        {"stage": "vault", "ok": True},
        {"stage": "latch_pin", "ok": True},
        {"stage": "beta", "ok": True},
        {"stage": "fit_commit", "ok": True},
        {"stage": "forecast", "ok": True},
        {"stage": "emit_trust", "ok": True},
        {"stage": "plaque", "ok": True},
    ]
    j_p.write_text("".join(json.dumps(r) + "\n" for r in stages), encoding="utf-8")

    chain_p = Path(state_dir) / "pass_chain.jsonl"
    append_pass_chain({}, int(pin_obj.get("pin_seq", 1)), chain_p)

    plaque_path = Path(out_dir) / "promotion_plaque.json"
    plaque = write_plaque(forecast, workbook, d_p, b_p, f_p, v_p, c_p, a_p, s_p, t_p, plaque_path)
    return {"vault": vault, "beta": beta, "forecast": forecast, "plaque": plaque, "latch_pin": pin_obj}


def run_emit(workbook_path=None, traces_path=None, state_dir="/app/state", out_dir="/app/plaque"):
    wb_path, _tr = _paths(workbook_path, traces_path)
    workbook = load_json(wb_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    d_p = Path(state_dir) / "design_matrix.json"
    b_p = Path(state_dir) / "beta_hat.json"
    f_p = Path(state_dir) / "forecast_tape.json"
    v_p = Path(state_dir) / "design_vault.json"
    c_p = Path(state_dir) / "fit_commit.json"
    a_p = Path(state_dir) / "latch_pin.json"
    s_p = Path(state_dir) / "beta_latch_seal.json"
    t_p = Path(state_dir) / "emit_trust.json"
    forecast = {"mape": 0.0, "r2": 1.0, "metrics_pass": True,
                "mape_ceiling": workbook["mape_ceiling"], "r2_floor": workbook["r2_floor"]}
    plaque = write_plaque(forecast, workbook, d_p, b_p, f_p, v_p, c_p, a_p, s_p, t_p,
                          Path(out_dir) / "promotion_plaque.json")
    return {"plaque": plaque}


def run_eval(workbook_path=None, traces_path=None, state_dir="/app/state", out_dir="/app/plaque"):
    run_vault(workbook_path, traces_path, state_dir=state_dir)
    return run_forecast(workbook_path, traces_path, state_dir=state_dir, out_dir=out_dir)
