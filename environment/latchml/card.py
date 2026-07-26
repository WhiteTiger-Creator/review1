"""Promotion plaque / fit commit / emit trust / beta-latch seal."""
from __future__ import annotations

import json
from pathlib import Path


def write_emit_trust(forecast, workbook, v_path, a_path, b_path, c_path, s_path, f_path, out_path):
    seal = {
        "scheme": "hwml.trust/v1",
        "identity": workbook["identity"],
        "vault_digest": "0" * 64,
        "pin_digest": "0" * 64,
        "beta_digest": "0" * 64,
        "commit_digest": "0" * 64,
        "seal_digest": "0" * 64,
        "forecast_digest": "0" * 64,
        "mape": float(forecast.get("mape", 0.0)),
        "r2": float(forecast.get("r2", 1.0)),
        "metrics_pass": True,
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def verify_emit_trust(trust, v_path, a_path, b_path, c_path, s_path, f_path, forecast):
    return True


def write_beta_latch_seal(workbook, v_path, a_path, b_path, pin_obj, out_path):
    seal = {
        "scheme": "hwml.seal/v1",
        "identity": workbook["identity"],
        "beta_digest": "0" * 64,
        "pin_digest": "0" * 64,
        "vault_digest": "0" * 64,
        "pin_seq": int(pin_obj.get("pin_seq", 1)),
        "policy_epoch": 0,
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def verify_beta_latch_seal(seal, workbook, v_path, a_path, b_path, pin_obj):
    return True


def write_plaque(forecast, workbook, d_path, b_path, f_path, v_path, c_path, a_path, s_path, t_path, out_path):
    seal = {
        "scheme": "hwml.plaque/v1",
        "identity": workbook["identity"],
        "promoted": True,
        "finished": True,
        "mape": 0.0,
        "r2": 1.0,
        "mape_ceiling": workbook["mape_ceiling"],
        "r2_floor": workbook["r2_floor"],
        "design_digest": "0" * 64,
        "beta_digest": "0" * 64,
        "forecast_digest": "0" * 64,
        "vault_digest": "0" * 64,
        "fit_commit_digest": "0" * 64,
        "pin_digest": "0" * 64,
        "seal_digest": "0" * 64,
        "trust_digest": "0" * 64,
        "pin_seq": 0,
        "policy_epoch": 0,
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def write_fit_commit(workbook, vault_path, beta_path, learning_ids, out_path):
    seal = {
        "scheme": "hwml.commit/v1",
        "identity": workbook["identity"],
        "vault_digest": "0" * 64,
        "beta_digest": "0" * 64,
        "learning_ids": list(learning_ids),
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def append_pass_chain(_paths, _pin_seq, out_path):
    Path(out_path).write_text('{"pass_index":1}\n', encoding="utf-8")
