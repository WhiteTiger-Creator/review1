"""Verifier for offline bandit IPS / DR evaluation against the protocol."""

from __future__ import annotations

import json
import math
from pathlib import Path

OUT = Path("/app/output/ips_eval.json")
DATA = Path("/app/data")
FEATURES = Path("/app/features")
MODELS = Path("/app/models")
CFG = Path("/app/config/eval.json")
SRC = Path("/app/bandit")

TOL = 1e-9
CUTOFF = 1_704_067_200
WINDOW = 604_800
CLIP_MAX = 10.0
PROP_FLOOR = 0.01
ESS_THR = 50.0
CI_THR = 0.12
VALUE_FLOOR = 0.15


def _load_report():
    with open(OUT) as f:
        return json.load(f)


def _read_jsonl(path: Path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _round6(v: float) -> float:
    return round(v + 0.0, 6)


def _expected():
    cfg = json.loads(CFG.read_text())
    target = json.loads((MODELS / "target_policy.json").read_text())
    reward = json.loads((MODELS / "reward_model.json").read_text())
    schema = json.loads((FEATURES / "action_schema.json").read_text())
    actions = list(schema["actions"])
    events = _read_jsonl(DATA / "logs" / "interactions.jsonl")

    cutoff = int(cfg["cutoff_unix"])
    window = int(cfg["eval_window_sec"])

    in_window = [e for e in events if cutoff <= int(e["timestamp"]) < cutoff + window]
    floor_excluded = sum(1 for e in in_window if float(e["propensity"]) < PROP_FLOOR)
    kept = [e for e in in_window if float(e["propensity"]) >= PROP_FLOOR]

    rows = []
    for e in kept:
        cid = e["context_id"]
        a = e["action"]
        if cid not in target["by_context"] or a not in target["by_context"][cid]:
            continue
        if cid not in reward["by_context"] or a not in reward["by_context"][cid]:
            continue
        pi_e = float(target["by_context"][cid][a])
        pi_b = float(e["propensity"])
        w = pi_e / pi_b
        w = min(w, CLIP_MAX)
        qhat = float(reward["by_context"][cid][a])
        direct = sum(
            float(target["by_context"][cid][aa]) * float(reward["by_context"][cid][aa])
            for aa in actions
        )
        rows.append(
            {
                "action": a,
                "reward": float(e["reward"]),
                "w": w,
                "qhat": qhat,
                "direct": direct,
            }
        )

    n = len(rows)
    ws = [r["w"] for r in rows]
    wr = [r["w"] * r["reward"] for r in rows]
    sum_w = sum(ws)
    sum_w2 = sum(w * w for w in ws)
    sum_wr = sum(wr)

    ips = _round6(sum_wr / n) if n else 0.0
    snips = _round6(sum_wr / sum_w) if sum_w else 0.0
    dr = (
        _round6(sum(r["w"] * (r["reward"] - r["qhat"]) + r["direct"] for r in rows) / n)
        if n
        else 0.0
    )
    ess = _round6((sum_w * sum_w) / sum_w2) if sum_w2 else 0.0
    mean_wr = (sum_wr / n) if n else 0.0
    var_wr = sum((x - mean_wr) ** 2 for x in wr) / n if n else 0.0
    ci = _round6(1.96 * math.sqrt(var_wr / n)) if n else 0.0
    policy_value = snips
    score = max(0.0, round(100.0 - 80.0 * abs(1.0 - ess / max(n, 1)) - 200.0 * ci, 2))
    serve_block = ess < ESS_THR or ci > CI_THR or policy_value < VALUE_FLOOR

    arms = []
    for a in sorted(actions):
        arm_rows = [r for r in rows if r["action"] == a]
        an = len(arm_rows)
        if an == 0:
            arms.append(
                {
                    "action": a,
                    "n": 0,
                    "included": False,
                    "exclude_reason": "EMPTY_ARM",
                    "mean_weight": 0.0,
                    "ips_contrib": 0.0,
                    "mean_reward": 0.0,
                    "flagged": False,
                    "flag_reason": "",
                }
            )
            continue
        mw = sum(r["w"] for r in arm_rows) / an
        ips_c = sum(r["w"] * r["reward"] for r in arm_rows) / n
        mr = sum(r["reward"] for r in arm_rows) / an
        flagged = mw > CLIP_MAX * 0.9
        arms.append(
            {
                "action": a,
                "n": an,
                "included": True,
                "exclude_reason": "",
                "mean_weight": _round6(mw),
                "ips_contrib": _round6(ips_c),
                "mean_reward": _round6(mr),
                "flagged": flagged,
                "flag_reason": "HEAVY_WEIGHT" if flagged else "",
            }
        )

    return {
        "schema_version": "1.0",
        "policy_source": "offline-bandit-ips-v1",
        "window": {
            "cutoff_unix": CUTOFF,
            "eval_window_sec": WINDOW,
            "eval_rows": n,
            "floor_excluded": floor_excluded,
            "arms_evaluated": sum(1 for a in arms if a["included"]),
            "arms_flagged": sum(1 for a in arms if a["flagged"]),
        },
        "metrics": {
            "policy_value": policy_value,
            "ips": ips,
            "snips": snips,
            "dr": dr,
            "ess": ess,
            "ci_half_width": ci,
            "policy_score": score,
            "serve_block": serve_block,
        },
        "arms": arms,
        "calibration": {
            "clip_max": 10.0,
            "propensity_floor": 0.01,
            "ess_threshold": 50.0,
            "ci_threshold": 0.12,
            "value_floor": 0.15,
            "estimator": "snips",
            "weight_mode": "clipped_ratio",
            "dr_mode": "residual_direct",
            "aggregate": "macro",
        },
    }


def test_report_exists():
    """ips_eval.json must be produced under /app/output."""
    assert OUT.is_file(), "missing /app/output/ips_eval.json"


def test_top_level_keys():
    """Report must expose schema_version, policy_source, window, metrics, arms, calibration."""
    rep = _load_report()
    for k in ("schema_version", "policy_source", "window", "metrics", "arms", "calibration"):
        assert k in rep


def test_identity_stamps():
    """schema_version and policy_source must match the offline bandit IPS protocol."""
    rep = _load_report()
    assert rep["schema_version"] == "1.0"
    assert rep["policy_source"] == "offline-bandit-ips-v1"


def test_window_counts():
    """Window counters must reflect temporal filter, propensity floor, and arm flags."""
    exp = _expected()
    rep = _load_report()
    assert rep["window"] == exp["window"]


def test_calibration_identities():
    """Calibration stamps must match protocol identities used for scoring."""
    exp = _expected()
    rep = _load_report()
    assert rep["calibration"] == exp["calibration"]


def test_metrics_match_protocol():
    """Aggregate IPS, SNIPS, DR, ESS, CI, policy_value, score, and serve_block must match."""
    exp = _expected()
    rep = _load_report()
    for k, v in exp["metrics"].items():
        if isinstance(v, float):
            assert abs(rep["metrics"][k] - v) <= TOL, f"metrics.{k}: {rep['metrics'][k]} != {v}"
        else:
            assert rep["metrics"][k] == v, f"metrics.{k}"


def test_policy_value_is_snips():
    """Primary policy_value must equal SNIPS, not raw IPS."""
    rep = _load_report()
    assert abs(rep["metrics"]["policy_value"] - rep["metrics"]["snips"]) <= TOL
    assert abs(rep["metrics"]["policy_value"] - rep["metrics"]["ips"]) > 1e-12 or True
    exp = _expected()
    if abs(exp["metrics"]["snips"] - exp["metrics"]["ips"]) > 1e-9:
        assert abs(rep["metrics"]["policy_value"] - rep["metrics"]["ips"]) > 1e-9


def test_arms_sorted_and_complete():
    """Arms array lists every schema action sorted ascending by action id."""
    schema = json.loads((FEATURES / "action_schema.json").read_text())
    rep = _load_report()
    got = [a["action"] for a in rep["arms"]]
    assert got == sorted(schema["actions"])


def test_per_arm_metrics():
    """Per-arm mean_weight, ips_contrib, mean_reward, and flags must match the protocol."""
    exp = _expected()
    rep = _load_report()
    assert len(rep["arms"]) == len(exp["arms"])
    for ea, ga in zip(exp["arms"], rep["arms"]):
        assert ga["action"] == ea["action"]
        assert ga["n"] == ea["n"]
        assert ga["included"] == ea["included"]
        assert ga["exclude_reason"] == ea["exclude_reason"]
        assert abs(ga["mean_weight"] - ea["mean_weight"]) <= TOL
        assert abs(ga["ips_contrib"] - ea["ips_contrib"]) <= TOL
        assert abs(ga["mean_reward"] - ea["mean_reward"]) <= TOL
        assert ga["flagged"] == ea["flagged"]
        assert ga["flag_reason"] == ea["flag_reason"]


def test_floor_exclusion_applied():
    """Propensity-floor exclusions must be counted and must shrink eval_rows."""
    exp = _expected()
    rep = _load_report()
    assert rep["window"]["floor_excluded"] == exp["window"]["floor_excluded"]
    assert exp["window"]["floor_excluded"] > 0
    events = _read_jsonl(DATA / "logs" / "interactions.jsonl")
    in_window = sum(1 for e in events if CUTOFF <= int(e["timestamp"]) < CUTOFF + WINDOW)
    assert rep["window"]["eval_rows"] == in_window - rep["window"]["floor_excluded"]


def test_serve_block_logic():
    """serve_block is true when ESS/CI/value_floor gates breach protocol thresholds."""
    rep = _load_report()
    exp = _expected()
    assert rep["metrics"]["serve_block"] == exp["metrics"]["serve_block"]
    expect_block = (
        rep["metrics"]["ess"] < ESS_THR
        or rep["metrics"]["ci_half_width"] > CI_THR
        or rep["metrics"]["policy_value"] < VALUE_FLOOR
    )
    assert rep["metrics"]["serve_block"] is expect_block


def test_ess_not_shortlist_heuristic():
    """ESS must use (sum w)^2 / sum(w^2), not N / max(w)."""
    exp = _expected()
    rep = _load_report()
    assert abs(rep["metrics"]["ess"] - exp["metrics"]["ess"]) <= TOL
    # Independent shortlist heuristic on protocol weights should differ on this fixture.
    cfg = json.loads(CFG.read_text())
    target = json.loads((MODELS / "target_policy.json").read_text())
    events = _read_jsonl(DATA / "logs" / "interactions.jsonl")
    cutoff = int(cfg["cutoff_unix"])
    window = int(cfg["eval_window_sec"])
    weights = []
    for e in events:
        if not (cutoff <= int(e["timestamp"]) < cutoff + window):
            continue
        if float(e["propensity"]) < PROP_FLOOR:
            continue
        pi_e = float(target["by_context"][e["context_id"]][e["action"]])
        w = pi_e / float(e["propensity"])
        w = min(w, CLIP_MAX)
        weights.append(w)
    shortlist = len(weights) / max(weights) if weights else 0.0
    assert abs(shortlist - exp["metrics"]["ess"]) > 1e-6


def test_weights_not_inverted():
    """IPS must use π_e/π_b clipped ratios; inverted π_b/π_e must not match."""
    exp = _expected()
    rep = _load_report()
    assert abs(rep["metrics"]["ips"] - exp["metrics"]["ips"]) <= TOL
    cfg = json.loads(CFG.read_text())
    target = json.loads((MODELS / "target_policy.json").read_text())
    events = _read_jsonl(DATA / "logs" / "interactions.jsonl")
    cutoff = int(cfg["cutoff_unix"])
    window = int(cfg["eval_window_sec"])
    inv = []
    for e in events:
        if not (cutoff <= int(e["timestamp"]) < cutoff + window):
            continue
        if float(e["propensity"]) < PROP_FLOOR:
            continue
        pi_e = float(target["by_context"][e["context_id"]][e["action"]])
        w = float(e["propensity"]) / pi_e
        inv.append(w * float(e["reward"]))
    inverted_ips = _round6(sum(inv) / len(inv)) if inv else 0.0
    assert abs(inverted_ips - exp["metrics"]["ips"]) > 1e-6


def test_dr_uses_residual_direct():
    """DR must apply residual correction plus direct method, not IPS-only surrogates."""
    exp = _expected()
    rep = _load_report()
    assert abs(rep["metrics"]["dr"] - exp["metrics"]["dr"]) <= TOL
    # IPS + mean(direct) surrogate should differ from residual_direct on this fixture.
    assert abs(rep["metrics"]["dr"] - rep["metrics"]["ips"]) > 1e-9 or True
    if abs(exp["metrics"]["dr"] - exp["metrics"]["ips"]) > 1e-6:
        assert abs(rep["metrics"]["dr"] - rep["metrics"]["ips"]) > 1e-6


def test_fixture_integrity():
    """Logged interactions, target policy, and reward model must remain unmodified."""
    events = _read_jsonl(DATA / "logs" / "interactions.jsonl")
    assert len(events) >= 400
    assert any(e["event_id"] == "e0000" for e in events)
    target = json.loads((MODELS / "target_policy.json").read_text())
    assert target["policy_id"] == "target-v3"
    reward = json.loads((MODELS / "reward_model.json").read_text())
    assert reward["model_id"] == "qhat-v2"
    schema = json.loads((FEATURES / "action_schema.json").read_text())
    assert schema["actions"] == ["a0", "a1", "a2", "a3"]
    cfg = json.loads(CFG.read_text())
    assert cfg["overlay_profile"] == "dashboard"
    assert cfg["legacy_reconcile"] is False


def test_go_sources_present():
    """Evaluation must be emitted by the Go bandit sources under /app/bandit."""
    assert (SRC / "go.mod").is_file()
    assert (SRC / "cmd" / "ipseva" / "main.go").is_file()
    assert (SRC / "h8s" / "estimate.go").is_file()
    assert (SRC / "hparams" / "defaults.go").is_file()
    assert (SRC / "j3f" / "weight.go").is_file()
