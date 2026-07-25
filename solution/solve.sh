#!/usr/bin/env bash
# Oracle solve — task identity hallwarden-kotlin-postgres-codex-locks token 79eaafa5
# Oracle solve — hallwarden latch poly-OLS vault→forecast→emit (Case 6 Path C)
set -euo pipefail
mkdir -p /app/latchml /app/state /app/plaque
cat > /app/latchml/stage_io.py <<'ORACLE_EOF'
"""Stage JSON persistence — reload from disk."""
from __future__ import annotations
import json
from pathlib import Path


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return obj


def reload_json(path, _fallback):
    return json.loads(Path(path).read_text(encoding="utf-8"))
ORACLE_EOF
cat > /app/latchml/pinning.py <<'ORACLE_EOF'
"""Latch pin — SHA-256 of on-disk vault bytes + pin_seq reuse + policy_epoch."""
from __future__ import annotations
import hashlib
from pathlib import Path


def vault_digest(vault_path):
    return hashlib.sha256(Path(vault_path).read_bytes()).hexdigest()


def build_pin(vault, vault_path, prior=None):
    digest = vault_digest(vault_path)
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
ORACLE_EOF
cat > /app/latchml/features.py <<'ORACLE_EOF'
"""Design matrix builder — quadratic columns, id-sorted, trunc, policy_epoch."""
from __future__ import annotations
import math


def trunc(x, n):
    p = 10 ** n
    return math.trunc(x * p + (0.5 if x >= 0 else -0.5)) / p


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
ORACLE_EOF
cat > /app/latchml/fit.py <<'ORACLE_EOF'
"""OLS beta fit — learning cohort only; ignore ridge_lambda bait."""
from __future__ import annotations
import math


def trunc(x, n):
    p = 10 ** n
    return math.trunc(x * p + (0.5 if x >= 0 else -0.5)) / p


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


COL_NAMES = ["intercept", "mean", "max", "std", "mean_sq", "max_sq", "std_sq"]


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
ORACLE_EOF
cat > /app/latchml/score.py <<'ORACLE_EOF'
"""Reserved cohort forecast — MAPE/R2 dual AND gate."""
from __future__ import annotations
import math


def trunc(x, n):
    p = 10 ** n
    return math.trunc(x * p + (0.5 if x >= 0 else -0.5)) / p


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
ORACLE_EOF
cat > /app/latchml/card.py <<'ORACLE_EOF'
"""Promotion plaque + fit commit + emit trust + beta-latch seal + pass chain."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_fit_commit(workbook, vault_path, beta_path, learning_ids, out_path):
    seal = {
        "scheme": "hwml.commit/v1",
        "identity": workbook["identity"],
        "vault_digest": sha256_file(vault_path),
        "beta_digest": sha256_file(beta_path),
        "learning_ids": list(learning_ids),
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def write_beta_latch_seal(workbook, v_path, a_path, b_path, pin_obj, out_path):
    seal = {
        "scheme": "hwml.seal/v1",
        "identity": workbook["identity"],
        "beta_digest": sha256_file(b_path),
        "pin_digest": sha256_file(a_path),
        "vault_digest": sha256_file(v_path),
        "pin_seq": int(pin_obj["pin_seq"]),
        "policy_epoch": int(workbook["policy_epoch"]),
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def verify_beta_latch_seal(seal, workbook, v_path, a_path, b_path, pin_obj):
    if not isinstance(seal, dict) or seal.get("scheme") != "hwml.seal/v1":
        return False
    return (
        seal.get("beta_digest") == sha256_file(b_path)
        and seal.get("pin_digest") == sha256_file(a_path)
        and seal.get("vault_digest") == sha256_file(v_path)
        and int(seal.get("pin_seq", -1)) == int(pin_obj.get("pin_seq", -2))
        and int(seal.get("policy_epoch", -1)) == int(workbook["policy_epoch"])
    )


def write_emit_trust(forecast, workbook, v_path, a_path, b_path, c_path, s_path, f_path, out_path):
    seal = {
        "scheme": "hwml.trust/v1",
        "identity": workbook["identity"],
        "vault_digest": sha256_file(v_path),
        "pin_digest": sha256_file(a_path),
        "beta_digest": sha256_file(b_path),
        "commit_digest": sha256_file(c_path),
        "seal_digest": sha256_file(s_path),
        "forecast_digest": sha256_file(f_path),
        "mape": forecast["mape"],
        "r2": forecast["r2"],
        "metrics_pass": bool(forecast["metrics_pass"]),
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def verify_emit_trust(trust, v_path, a_path, b_path, c_path, s_path, f_path, forecast):
    if not isinstance(trust, dict) or trust.get("scheme") != "hwml.trust/v1":
        return False
    return (
        trust.get("vault_digest") == sha256_file(v_path)
        and trust.get("pin_digest") == sha256_file(a_path)
        and trust.get("beta_digest") == sha256_file(b_path)
        and trust.get("commit_digest") == sha256_file(c_path)
        and trust.get("seal_digest") == sha256_file(s_path)
        and trust.get("forecast_digest") == sha256_file(f_path)
        and float(trust.get("mape")) == float(forecast["mape"])
        and float(trust.get("r2")) == float(forecast["r2"])
        and bool(trust.get("metrics_pass")) == bool(forecast["metrics_pass"])
    )


def write_plaque(forecast, workbook, d_path, b_path, f_path, v_path, c_path, a_path, s_path, t_path, out_path):
    pin = json.loads(Path(a_path).read_text(encoding="utf-8"))
    trust = json.loads(Path(t_path).read_text(encoding="utf-8"))
    seal = {
        "scheme": "hwml.plaque/v1",
        "identity": workbook["identity"],
        "promoted": bool(trust["metrics_pass"]),
        "finished": True,
        "mape": trust["mape"],
        "r2": trust["r2"],
        "mape_ceiling": forecast["mape_ceiling"],
        "r2_floor": forecast["r2_floor"],
        "design_digest": sha256_file(d_path),
        "beta_digest": sha256_file(b_path),
        "forecast_digest": sha256_file(f_path),
        "vault_digest": sha256_file(v_path),
        "fit_commit_digest": sha256_file(c_path),
        "pin_digest": sha256_file(a_path),
        "seal_digest": sha256_file(s_path),
        "trust_digest": sha256_file(t_path),
        "pin_seq": int(pin.get("pin_seq", 1)),
        "policy_epoch": int(workbook["policy_epoch"]),
    }
    Path(out_path).write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8")
    return seal


def append_pass_chain(v_path, a_path, b_path, c_path, s_path, f_path, t_path, pin_seq, out_path):
    out = Path(out_path)
    prior = ""
    pass_index = 1
    if out.is_file():
        lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            last = json.loads(lines[-1])
            prior = last.get("chain_digest", "")
            pass_index = len(lines) + 1
    parts = [
        sha256_file(v_path),
        sha256_file(a_path),
        sha256_file(b_path),
        sha256_file(c_path),
        sha256_file(s_path),
        sha256_file(f_path),
        sha256_file(t_path),
    ]
    fp = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    vd = sha256_file(v_path)
    sd = sha256_file(s_path)
    pin_seq = int(pin_seq)
    blob = f"{prior}|{fp}|{vd}|{sd}|{pin_seq}|{pass_index}"
    row = {
        "pass_index": pass_index,
        "prior_digest": prior,
        "stage_fingerprint": fp,
        "vault_digest": vd,
        "seal_digest": sd,
        "pin_seq": pin_seq,
        "chain_digest": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
    }
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row
ORACLE_EOF
cat > /app/latchml/driver.py <<'ORACLE_EOF'
"""Eval driver — vault then forecast then emit; seal/trust verified; pass chain."""
from __future__ import annotations
import hashlib
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
    verify_emit_trust,
    write_beta_latch_seal,
    verify_beta_latch_seal,
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

    a_p = Path(state_dir) / "latch_pin.json"
    prior = load_json(a_p) if a_p.is_file() else None
    pin_obj = pin_mod.build_pin(vault, v_p, prior)
    stage_io.write_json(a_p, pin_obj)
    return {"design": design, "vault": vault, "latch_pin": pin_obj}


def run_forecast(workbook_path=None, traces_path=None, state_dir="/app/state", out_dir="/app/plaque"):
    wb_path, _tr = _paths(workbook_path, traces_path)
    workbook = load_json(wb_path)
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    v_p = Path(state_dir) / "design_vault.json"
    a_p = Path(state_dir) / "latch_pin.json"
    d_p = Path(state_dir) / "design_matrix.json"
    if not v_p.is_file() or not a_p.is_file():
        raise SystemExit("missing staged vault or latch_pin")

    vault = stage_io.reload_json(v_p, None)
    pin_obj = stage_io.reload_json(a_p, None)
    fresh = hashlib.sha256(v_p.read_bytes()).hexdigest()
    if pin_obj.get("vault_digest") != fresh:
        raise SystemExit("latch_pin vault_digest mismatch")
    if int(vault.get("policy_epoch", -1)) != int(workbook["policy_epoch"]):
        raise SystemExit("vault policy_epoch mismatch")

    beta = fit_beta(vault, workbook)
    b_p = Path(state_dir) / "beta_hat.json"
    stage_io.write_json(b_p, beta)
    beta = stage_io.reload_json(b_p, beta)

    learning_ids = [r["id"] for r in vault["rows"] if r["cohort"] == "learning"]
    c_p = Path(state_dir) / "fit_commit.json"
    write_fit_commit(workbook, v_p, b_p, learning_ids, c_p)

    s_p = Path(state_dir) / "beta_latch_seal.json"
    write_beta_latch_seal(workbook, v_p, a_p, b_p, pin_obj, s_p)
    seal = stage_io.reload_json(s_p, None)
    if not verify_beta_latch_seal(seal, workbook, v_p, a_p, b_p, pin_obj):
        raise SystemExit("beta_latch_seal verification failed")

    forecast = forecast_reserved(vault, beta, workbook)
    f_p = Path(state_dir) / "forecast_tape.json"
    stage_io.write_json(f_p, forecast)
    forecast = stage_io.reload_json(f_p, forecast)

    t_p = Path(state_dir) / "emit_trust.json"
    write_emit_trust(forecast, workbook, v_p, a_p, b_p, c_p, s_p, f_p, t_p)
    trust = stage_io.reload_json(t_p, None)
    if not verify_emit_trust(trust, v_p, a_p, b_p, c_p, s_p, f_p, forecast):
        raise SystemExit("emit_trust verification failed")

    j_p = Path(state_dir) / "run_log.jsonl"
    stages = [
        {"stage": "design", "ok": True},
        {"stage": "vault", "ok": True},
        {"stage": "latch_pin", "ok": True},
        {"stage": "beta", "ok": True},
        {"stage": "commit", "ok": True},
        {"stage": "seal", "ok": True},
        {"stage": "forecast", "ok": True},
        {"stage": "trust", "ok": True},
        {"stage": "plaque", "ok": True},
    ]
    j_p.write_text("".join(json.dumps(r) + "\n" for r in stages), encoding="utf-8")

    chain_p = Path(state_dir) / "pass_chain.jsonl"
    append_pass_chain(v_p, a_p, b_p, c_p, s_p, f_p, t_p, int(pin_obj.get("pin_seq", 1)), chain_p)

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
    for p in (d_p, b_p, f_p, v_p, c_p, a_p, s_p, t_p):
        if not p.is_file():
            raise SystemExit(f"missing staged artifact {p.name}")
    forecast = stage_io.reload_json(f_p, None)
    pin_obj = stage_io.reload_json(a_p, None)
    trust = stage_io.reload_json(t_p, None)
    seal = stage_io.reload_json(s_p, None)
    if not verify_emit_trust(trust, v_p, a_p, b_p, c_p, s_p, f_p, forecast):
        raise SystemExit("emit_trust stale or mismatched")
    if not verify_beta_latch_seal(seal, workbook, v_p, a_p, b_p, pin_obj):
        raise SystemExit("beta_latch_seal stale or mismatched")
    plaque = write_plaque(forecast, workbook, d_p, b_p, f_p, v_p, c_p, a_p, s_p, t_p,
                          Path(out_dir) / "promotion_plaque.json")
    return {"plaque": plaque, "forecast": forecast, "trust": trust}


def run_eval(workbook_path=None, traces_path=None, state_dir="/app/state", out_dir="/app/plaque"):
    run_vault(workbook_path, traces_path, state_dir=state_dir)
    return run_forecast(workbook_path, traces_path, state_dir=state_dir, out_dir=out_dir)
ORACLE_EOF

test -x /app/binx/hwml
/app/scripts/run-eval.sh
python3 - <<'CHK'
import json
from pathlib import Path
c = json.loads(Path("/app/plaque/promotion_plaque.json").read_text())
assert c["scheme"] == "hwml.plaque/v1" and c["promoted"] is True
assert "vault_digest" in c and "fit_commit_digest" in c and "pin_digest" in c
assert "seal_digest" in c and "trust_digest" in c and "policy_epoch" in c
v = json.loads(Path("/app/state/design_vault.json").read_text())
assert v["scheme"] == "hwml.vault/v1" and "policy_epoch" in v
pin = json.loads(Path("/app/state/latch_pin.json").read_text())
assert pin["scheme"] == "hwml.pin/v1" and "policy_epoch" in pin
fc = json.loads(Path("/app/state/fit_commit.json").read_text())
assert fc["scheme"] == "hwml.commit/v1"
seal = json.loads(Path("/app/state/beta_latch_seal.json").read_text())
assert seal["scheme"] == "hwml.seal/v1"
tr = json.loads(Path("/app/state/emit_trust.json").read_text())
assert tr["scheme"] == "hwml.trust/v1" and "seal_digest" in tr
chain = Path("/app/state/pass_chain.jsonl").read_text().strip().splitlines()
assert len(chain) >= 1
print("oracle_hwml_ok")
CHK
