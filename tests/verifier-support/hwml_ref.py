"""Poly-OLS latch energy reference math with vault + seal + pass chain."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def trunc(x, n):
    p = 10 ** n
    return math.trunc(x * p + (0.5 if x >= 0 else -0.5)) / p


def load_workbook(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_traces(path: Path) -> list:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def base_x(ticks):
    n = len(ticks)
    m = sum(ticks) / n
    mx = max(ticks)
    var = sum((t - m) ** 2 for t in ticks) / n
    return m, mx, math.sqrt(var)


def expand_row(ticks, nd):
    x1, x2, x3 = base_x([float(t) for t in ticks])
    cols = [1.0, x1, x2, x3, x1 * x1, x2 * x2, x3 * x3]
    return [trunc(c, nd) for c in cols]


COL_NAMES = ["intercept", "mean", "max", "std", "mean_sq", "max_sq", "std_sq"]


def build_design(traces, workbook):
    nd = int(workbook["trunc_decimals"])
    epoch = int(workbook["policy_epoch"])
    rows = []
    for t in traces:
        rows.append({
            "id": t["id"],
            "cohort": t["cohort"],
            "columns": expand_row(t["ticks"], nd),
            "target_energy": float(t["target_energy"]),
        })
    rows.sort(key=lambda r: r["id"])
    return {
        "scheme": "hwml.design/v1",
        "identity": workbook["identity"],
        "column_names": COL_NAMES,
        "rows": rows,
        "policy_epoch": epoch,
    }


def build_vault(design, source_trace_count):
    return {
        "scheme": "hwml.vault/v1",
        "identity": design["identity"],
        "column_names": list(design["column_names"]),
        "rows": list(design["rows"]),
        "source_trace_count": int(source_trace_count),
        "policy_epoch": int(design["policy_epoch"]),
    }


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def _mat_vec(a, v):
    return [sum(a[i][j] * v[j] for j in range(len(v))) for i in range(len(a))]


def _transpose(a):
    return [list(r) for r in zip(*a)]


def _invert(m):
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        a[col], a[piv] = a[piv], a[col]
        div = a[col][col]
        a[col] = [x / div for x in a[col]]
        for r in range(n):
            if r == col:
                continue
            f = a[r][col]
            a[r] = [a[r][c] - f * a[col][c] for c in range(2 * n)]
    return [row[n:] for row in a]


def fit_beta(design, workbook):
    nd = int(workbook["trunc_decimals"])
    learn = [r for r in design["rows"] if r["cohort"] == "learning"]
    learn = sorted(learn, key=lambda r: r["id"])
    X = [r["columns"] for r in learn]
    y = [r["target_energy"] for r in learn]
    Xt = _transpose(X)
    w = _mat_vec(_invert(_mat_mul(Xt, X)), _mat_vec(Xt, y))
    return {
        "scheme": "hwml.beta/v1",
        "identity": workbook["identity"],
        "names": list(COL_NAMES),
        "values": [trunc(v, nd) for v in w],
    }


def predict(cols, beta):
    return sum(c * b for c, b in zip(cols, beta["values"]))


def forecast_reserved(design, beta, workbook):
    nd = int(workbook["trunc_decimals"])
    reserved = [r for r in design["rows"] if r["cohort"] == "reserved"]
    reserved = sorted(reserved, key=lambda r: r["id"])
    rows = []
    for r in reserved:
        pred = trunc(predict(r["columns"], beta), nd)
        y = r["target_energy"]
        rows.append({
            "id": r["id"],
            "prediction": pred,
            "target_energy": y,
            "abs_pct": trunc(abs(y - pred) / max(abs(y), 1e-6), nd),
        })
    if rows:
        mape = trunc(sum(r["abs_pct"] for r in rows) / len(rows), nd)
        ybar = sum(r["target_energy"] for r in rows) / len(rows)
        ss_tot = sum((r["target_energy"] - ybar) ** 2 for r in rows)
        ss_res = sum((r["target_energy"] - r["prediction"]) ** 2 for r in rows)
        r2 = trunc(1.0 - (ss_res / ss_tot if ss_tot else 0.0), nd)
    else:
        mape, r2 = 0.0, 0.0
    mape_ok = mape <= float(workbook["mape_ceiling"])
    r2_ok = r2 >= float(workbook["r2_floor"])
    return {
        "scheme": "hwml.forecast/v1",
        "identity": workbook["identity"],
        "rows": rows,
        "mape": mape,
        "r2": r2,
        "mape_ceiling": float(workbook["mape_ceiling"]),
        "r2_floor": float(workbook["r2_floor"]),
        "metrics_pass": bool(rows) and mape_ok and r2_ok,
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_pin(vault, vault_path, prior=None):
    digest = sha256_file(vault_path)
    if isinstance(prior, dict) and prior.get("vault_digest") == digest:
        pin_seq = int(prior.get("pin_seq", 1))
    else:
        base = int(prior.get("pin_seq", 0)) if isinstance(prior, dict) else 0
        pin_seq = base + 1
    return {
        "scheme": "hwml.pin/v1",
        "vault_digest": digest,
        "row_count": len(vault.get("rows", [])),
        "identity": vault.get("identity"),
        "pin_seq": pin_seq,
        "policy_epoch": int(vault.get("policy_epoch", 0)),
    }


def build_fit_commit(workbook, vault_path, beta_path, learning_ids):
    return {
        "scheme": "hwml.commit/v1",
        "identity": workbook["identity"],
        "vault_digest": sha256_file(vault_path),
        "beta_digest": sha256_file(beta_path),
        "learning_ids": list(learning_ids),
    }


def build_seal(workbook, vault_path, pin_path, beta_path, pin_obj):
    return {
        "scheme": "hwml.seal/v1",
        "identity": workbook["identity"],
        "beta_digest": sha256_file(beta_path),
        "pin_digest": sha256_file(pin_path),
        "vault_digest": sha256_file(vault_path),
        "pin_seq": int(pin_obj["pin_seq"]),
        "policy_epoch": int(workbook["policy_epoch"]),
    }


def seal_matches(seal, workbook, vault_path, pin_path, beta_path, pin_obj):
    if not isinstance(seal, dict) or seal.get("scheme") != "hwml.seal/v1":
        return False
    return (
        seal.get("beta_digest") == sha256_file(beta_path)
        and seal.get("pin_digest") == sha256_file(pin_path)
        and seal.get("vault_digest") == sha256_file(vault_path)
        and int(seal.get("pin_seq", -1)) == int(pin_obj.get("pin_seq", -2))
        and int(seal.get("policy_epoch", -1)) == int(workbook["policy_epoch"])
    )


def build_emit_trust(forecast, workbook, vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path):
    return {
        "scheme": "hwml.trust/v1",
        "identity": workbook["identity"],
        "vault_digest": sha256_file(vault_path),
        "pin_digest": sha256_file(pin_path),
        "beta_digest": sha256_file(beta_path),
        "commit_digest": sha256_file(commit_path),
        "seal_digest": sha256_file(seal_path),
        "forecast_digest": sha256_file(forecast_path),
        "mape": forecast["mape"],
        "r2": forecast["r2"],
        "metrics_pass": bool(forecast["metrics_pass"]),
    }


def trust_matches(trust, vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path, forecast):
    if not isinstance(trust, dict):
        return False
    checks = [
        trust.get("scheme") == "hwml.trust/v1",
        trust.get("vault_digest") == sha256_file(vault_path),
        trust.get("pin_digest") == sha256_file(pin_path),
        trust.get("beta_digest") == sha256_file(beta_path),
        trust.get("commit_digest") == sha256_file(commit_path),
        trust.get("seal_digest") == sha256_file(seal_path),
        trust.get("forecast_digest") == sha256_file(forecast_path),
        float(trust.get("mape")) == float(forecast["mape"]),
        float(trust.get("r2")) == float(forecast["r2"]),
        bool(trust.get("metrics_pass")) == bool(forecast["metrics_pass"]),
    ]
    return all(checks)


def build_plaque(forecast, workbook, design_path, beta_path, forecast_path, vault_path, commit_path, latch_pin_path, seal_path, trust_path):
    latch_pin = json.loads(Path(latch_pin_path).read_text(encoding="utf-8"))
    trust = json.loads(Path(trust_path).read_text(encoding="utf-8"))
    return {
        "scheme": "hwml.plaque/v1",
        "identity": workbook["identity"],
        "promoted": bool(trust["metrics_pass"]),
        "finished": True,
        "mape": trust["mape"],
        "r2": trust["r2"],
        "mape_ceiling": forecast["mape_ceiling"],
        "r2_floor": forecast["r2_floor"],
        "design_digest": sha256_file(design_path),
        "beta_digest": sha256_file(beta_path),
        "forecast_digest": sha256_file(forecast_path),
        "vault_digest": sha256_file(vault_path),
        "fit_commit_digest": sha256_file(commit_path),
        "pin_digest": sha256_file(latch_pin_path),
        "seal_digest": sha256_file(seal_path),
        "trust_digest": sha256_file(trust_path),
        "pin_seq": int(latch_pin.get("pin_seq", 1)),
        "policy_epoch": int(workbook["policy_epoch"]),
    }


def stage_fingerprint(vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path, trust_path):
    parts = [
        sha256_file(vault_path),
        sha256_file(pin_path),
        sha256_file(beta_path),
        sha256_file(commit_path),
        sha256_file(seal_path),
        sha256_file(forecast_path),
        sha256_file(trust_path),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def chain_digest(prior_digest, fingerprint, vault_digest, seal_digest, pin_seq, pass_index):
    blob = f"{prior_digest}|{fingerprint}|{vault_digest}|{seal_digest}|{pin_seq}|{pass_index}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_pass_chain_row(prior_digest, vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path, trust_path, pin_seq, pass_index):
    fp = stage_fingerprint(vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path, trust_path)
    vd = sha256_file(vault_path)
    sd = sha256_file(seal_path)
    return {
        "pass_index": int(pass_index),
        "prior_digest": prior_digest,
        "stage_fingerprint": fp,
        "vault_digest": vd,
        "seal_digest": sd,
        "pin_seq": int(pin_seq),
        "chain_digest": chain_digest(prior_digest, fp, vd, sd, int(pin_seq), int(pass_index)),
    }


def witness_digest(prior_digest, plaque_digest, trust_digest, seal_digest, pin_seq, witness_index):
    blob = f"{prior_digest}|{plaque_digest}|{trust_digest}|{seal_digest}|{pin_seq}|{witness_index}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_witness_row(prior_digest, plaque_path, trust_path, seal_path, pin_seq, witness_index):
    pd = sha256_file(plaque_path)
    td = sha256_file(trust_path)
    sd = sha256_file(seal_path)
    return {
        "witness_index": int(witness_index),
        "prior_digest": prior_digest,
        "plaque_digest": pd,
        "trust_digest": td,
        "seal_digest": sd,
        "pin_seq": int(pin_seq),
        "witness_digest": witness_digest(prior_digest, pd, td, sd, int(pin_seq), int(witness_index)),
    }


def run_reference(workbook_path: Path, traces_path: Path):
    wb = load_workbook(workbook_path)
    traces = load_traces(traces_path)
    design = build_design(traces, wb)
    vault = build_vault(design, len(traces))
    beta = fit_beta(design, wb)
    forecast = forecast_reserved(design, beta, wb)
    learning_ids = [r["id"] for r in design["rows"] if r["cohort"] == "learning"]
    return {
        "workbook": wb,
        "design": design,
        "vault": vault,
        "beta": beta,
        "forecast": forecast,
        "learning_ids": learning_ids,
    }


def reference_run(workbook_path, traces_path):
    return run_reference(workbook_path, traces_path)


def reference_plaque(forecast, workbook, design_path, beta_path, forecast_path, vault_path, commit_path, latch_pin_path, seal_path, trust_path):
    return build_plaque(forecast, workbook, design_path, beta_path, forecast_path, vault_path, commit_path, latch_pin_path, seal_path, trust_path)


def reference_fit_commit(workbook, vault_path, beta_path, learning_ids):
    return build_fit_commit(workbook, vault_path, beta_path, learning_ids)


def reference_pin(vault, vault_path, prior=None):
    return build_pin(vault, vault_path, prior)


def reference_seal(workbook, vault_path, pin_path, beta_path, pin_obj):
    return build_seal(workbook, vault_path, pin_path, beta_path, pin_obj)


def reference_trust(forecast, workbook, vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path):
    return build_emit_trust(forecast, workbook, vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path)


def reference_pass_chain_row(prior_digest, vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path, trust_path, pin_seq, pass_index):
    return build_pass_chain_row(prior_digest, vault_path, pin_path, beta_path, commit_path, seal_path, forecast_path, trust_path, pin_seq, pass_index)


def reference_witness_row(prior_digest, plaque_path, trust_path, seal_path, pin_seq, witness_index):
    return build_witness_row(prior_digest, plaque_path, trust_path, seal_path, pin_seq, witness_index)
