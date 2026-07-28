"""Verifier — wind tunnel aerodynamic coefficient lab calibration."""
from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

BINARY = "/usr/local/bin/wtac-validate"
PUBLIC = Path("/app/fixtures/campaigns")
HELD = Path(__file__).resolve().parent / "verifier-fixtures" / "campaigns"


def trapz(y: list[float], x: list[float]) -> float:
    total = 0.0
    for i in range(len(x) - 1):
        total += 0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i])
    return total


def slopes(xs: list[float], zs: list[float]) -> list[float]:
    n = len(xs)
    out = [0.0] * n
    if n == 1:
        return out
    out[0] = (zs[1] - zs[0]) / (xs[1] - xs[0])
    out[-1] = (zs[-1] - zs[-2]) / (xs[-1] - xs[-2])
    for i in range(1, n - 1):
        out[i] = (zs[i + 1] - zs[i - 1]) / (xs[i + 1] - xs[i - 1])
    return out


def load_campaign(d: Path) -> dict:
    return {
        name: json.loads((d / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("conditions", "geometry", "pressures", "balance", "tare_runs")
    }


def reference_q(cond: dict) -> float:
    return 0.5 * float(cond["rho_kg_m3"]) * float(cond["V_mps"]) ** 2


def reference_pairs(camp: dict, q_inf: float) -> list[dict]:
    cond = camp["conditions"]
    cps = {}
    for s in camp["pressures"]["samples"]:
        cps[str(s["tap_id"])] = (float(s["p_pa"]) - float(cond["p_inf_pa"])) / q_inf
    upper: dict[float, dict] = {}
    lower: dict[float, dict] = {}
    for tap in camp["geometry"]["taps"]:
        key = round(float(tap["x_c"]), 12)
        (upper if tap["surface"] == "upper" else lower)[key] = tap
    pairs = []
    for key in sorted(set(upper) & set(lower)):
        u, lo = upper[key], lower[key]
        pairs.append(
            {
                "x_c": float(u["x_c"]),
                "z_u": float(u["z_c"]),
                "z_l": float(lo["z_c"]),
                "Cp_u": cps[str(u["tap_id"])],
                "Cp_l": cps[str(lo["tap_id"])],
            }
        )
    return pairs


def reference_forces(pairs: list[dict], alpha_deg: float) -> dict:
    xs = [p["x_c"] for p in pairs]
    dcp = [p["Cp_l"] - p["Cp_u"] for p in pairs]
    su = slopes(xs, [p["z_u"] for p in pairs])
    sl = slopes(xs, [p["z_l"] for p in pairs])
    ax = [pairs[i]["Cp_u"] * su[i] - pairs[i]["Cp_l"] * sl[i] for i in range(len(pairs))]
    cn, ca = trapz(dcp, xs), trapz(ax, xs)
    a = alpha_deg * math.pi / 180.0
    return {
        "Cn": cn,
        "Ca": ca,
        "Cl": cn * math.cos(a) - ca * math.sin(a),
        "Cd": cn * math.sin(a) + ca * math.cos(a),
        "alpha_rad": a,
    }


def reference_cm(pairs: list[dict], xref: float) -> float:
    xs = [p["x_c"] for p in pairs]
    y = [(p["Cp_l"] - p["Cp_u"]) * (xref - p["x_c"]) for p in pairs]
    return trapz(y, xs)


def reference_tare(runs: list[dict]) -> dict:
    rows = [r for r in runs if not r["wind_on"]]
    n = float(len(rows))

    def mean(k: str) -> float:
        return sum(float(r[k]) for r in rows) / n

    def sigma(k: str, mu: float) -> float:
        return math.sqrt(sum((float(r[k]) - mu) ** 2 for r in rows) / (n - 1.0))

    mx, mz, mm = mean("Fx_N"), mean("Fz_N"), mean("My_Nm")
    return {
        "tare_run_count": len(rows),
        "mean_tare_Fx_N": mx,
        "mean_tare_Fz_N": mz,
        "mean_tare_My_Nm": mm,
        "sigma_tare_Fx_N": sigma("Fx_N", mx),
        "sigma_tare_Fz_N": sigma("Fz_N", mz),
        "sigma_tare_My_Nm": sigma("My_Nm", mm),
    }


def reference_balance(camp: dict, tare: dict, q_inf: float) -> dict:
    cond = camp["conditions"]
    s_ref = float(cond["chord_m"]) * float(cond["span_m"])
    fx = float(camp["balance"]["Fx_N"]) - tare["mean_tare_Fx_N"]
    fz = float(camp["balance"]["Fz_N"]) - tare["mean_tare_Fz_N"]
    my = float(camp["balance"]["My_Nm"]) - tare["mean_tare_My_Nm"]
    return {
        "Cl": fz / (q_inf * s_ref),
        "Cd": fx / (q_inf * s_ref),
        "Cm": my / (q_inf * s_ref * float(cond["chord_m"])),
        "corrected_Fx_N": fx,
        "corrected_Fz_N": fz,
        "corrected_My_Nm": my,
        "S_ref_m2": s_ref,
    }


def reference_unc(cond: dict, q_inf: float, pairs: list[dict], forces: dict, bal: dict) -> dict:
    rho, v = float(cond["rho_kg_m3"]), float(cond["V_mps"])
    u_rho, u_v, u_p = float(cond["u_rho_kg_m3"]), float(cond["u_V_mps"]), float(cond["u_p_pa"])
    rel_q = math.sqrt((u_rho / rho) ** 2 + (2.0 * u_v / v) ** 2)
    u_q = rel_q * q_inf
    u_cp = u_p / q_inf
    xs = [p["x_c"] for p in pairs]
    u_dcp = math.sqrt(2.0) * u_cp
    acc = 0.0
    for i in range(len(xs) - 1):
        w = 0.5 * (xs[i + 1] - xs[i])
        acc += 2.0 * (w * u_dcp) ** 2
    u_cn = math.sqrt(acc)
    u_cl_p = abs(math.cos(forces["alpha_rad"])) * u_cn
    u_cl_b = abs(bal["Cl"]) * rel_q
    u_rss = math.sqrt(u_cl_p**2 + u_cl_b**2)
    return {
        "u_q_inf_pa": u_q,
        "u_Cp": u_cp,
        "u_Cl_pressure": u_cl_p,
        "u_Cl_balance": u_cl_b,
        "u_Cl_rss": u_rss,
    }


def fnv_seal(campaign_id: str, q_inf: float, cl_p: float, cd_p: float, cm_p: float, cl_b: float) -> str:
    line = f"{campaign_id}|{q_inf:.8f}|{cl_p:.8f}|{cd_p:.8f}|{cm_p:.8f}|{cl_b:.8f}"
    h = 2166136261
    for byte in (line + "\n").encode("utf-8"):
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"


def run_feature(campaign: Path, work: Path | None = None) -> Path:
    work = work or Path(tempfile.mkdtemp(prefix="wtac-"))
    proc = subprocess.run(
        [BINARY, "feature", "--campaign-dir", str(campaign), "--work-dir", str(work)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return work


def run_eval(campaign: Path, work: Path) -> Path:
    proc = subprocess.run(
        [BINARY, "eval", "--campaign-dir", str(campaign), "--work-dir", str(work)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return work


def run_validate(campaign: Path) -> Path:
    work = run_feature(campaign)
    return run_eval(campaign, work)


def assert_close(a: float, b: float, tol: float = 1e-8, msg: str = "") -> None:
    assert abs(a - b) <= tol, f"{msg}: {a} vs {b} (tol={tol})"


# --- binary / layout ---


def test_eval_binary_installed():
    """Eval CLI binary must be installed at /usr/local/bin/wtac-validate after make build."""
    assert Path(BINARY).is_file()


def test_feature_public_campaigns_present():
    """Feature-batch public fixture campaigns listed in fixture-index must ship under /app/fixtures/campaigns."""
    for name in ("NACA0012-A4", "RAE2822-A2", "FLATPLATE-A0"):
        assert (PUBLIC / name / "conditions.json").is_file()


def test_model_api_symbols_importable():
    """Model API symbols from api-symbols.md must remain importable for attestation."""
    import wtac.core.errband as un
    import wtac.core.loadcell as bc
    import wtac.core.mref as pm
    import wtac.core.panel as fi
    import wtac.core.qinf as dyn
    import wtac.core.tapcp as pn
    import wtac.core.zeros as tc
    import wtac.decoy.decoy_pitot_blend as db
    import wtac.decoy.decoy_prandtl as dp
    import wtac.emit.emit_artifacts as em
    import wtac.feature.batch_stage as fs
    import wtac.io.load_campaign as lc

    for mod, name in [
        (lc, "wtac_load_campaign"),
        (dyn, "wtac_dynamic_pressure"),
        (pn, "wtac_pressure_coefficients"),
        (pn, "wtac_pair_stations"),
        (fi, "wtac_integrate_forces"),
        (pm, "wtac_pitching_moment"),
        (tc, "wtac_tare_stats"),
        (bc, "wtac_balance_coeffs"),
        (un, "wtac_uncertainty_budget"),
        (fs, "wtac_build_feature_batch"),
        (fs, "wtac_write_feature_batch"),
        (fs, "wtac_load_feature_batch"),
        (fs, "wtac_bump_feature_epoch"),
        (fs, "wtac_record_eval_success"),
        (em, "wtac_emit_artifacts"),
        (em, "wtac_report_seal"),
        (dp, "wtac_decoy_prandtl_q"),
        (db, "wtac_decoy_pitot_blend"),
    ]:
        assert callable(getattr(mod, name))


# --- public campaign numerical closure ---


@pytest.mark.parametrize("name", ["NACA0012-A4", "RAE2822-A2", "FLATPLATE-A0"])
def test_feature_dynamic_pressure_ignores_pitot(name):
    """Feature schema: dynamic-pressure feature must equal 0.5*rho*V^2 and must not equal pitot_q_pa."""
    camp = load_campaign(PUBLIC / name)
    work = run_validate(PUBLIC / name)
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    q = reference_q(camp["conditions"])
    assert_close(report["q_inf_pa"], q, 1e-9, "q_inf")
    assert abs(report["q_inf_pa"] - float(camp["conditions"]["pitot_q_pa"])) > 1.0


@pytest.mark.parametrize("name", ["NACA0012-A4", "RAE2822-A2", "FLATPLATE-A0"])
def test_model_inference_pressure_lift_drag_moment(name):
    """Model inference pressure-path coefficients must match trapezoidal integration with degree-to-radian alpha."""
    camp = load_campaign(PUBLIC / name)
    q = reference_q(camp["conditions"])
    pairs = reference_pairs(camp, q)
    forces = reference_forces(pairs, float(camp["conditions"]["alpha_deg"]))
    cm = reference_cm(pairs, float(camp["conditions"]["xref_c"]))
    work = run_validate(PUBLIC / name)
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["Cn"], forces["Cn"], 1e-8, "Cn")
    assert_close(report["Ca"], forces["Ca"], 1e-8, "Ca")
    assert_close(report["Cl_pressure"], forces["Cl"], 1e-8, "Cl")
    assert_close(report["Cd_pressure"], forces["Cd"], 1e-8, "Cd")
    assert_close(report["Cm_pressure"], cm, 1e-8, "Cm")
    assert_close(report["alpha_rad"], forces["alpha_rad"], 1e-12, "alpha")


@pytest.mark.parametrize("name", ["NACA0012-A4", "RAE2822-A2", "FLATPLATE-A0"])
def test_eval_metrics_balance_crosscheck(name):
    """Eval metrics: balance label coefficients after wind-off tare correction must close with pressure Cl within policy tolerance."""
    camp = load_campaign(PUBLIC / name)
    q = reference_q(camp["conditions"])
    pairs = reference_pairs(camp, q)
    forces = reference_forces(pairs, float(camp["conditions"]["alpha_deg"]))
    tare = reference_tare(camp["tare_runs"]["runs"])
    bal = reference_balance(camp, tare, q)
    work = run_validate(PUBLIC / name)
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["Cl_balance"], bal["Cl"], 1e-8, "Cl_b")
    assert_close(report["Cd_balance"], bal["Cd"], 1e-8, "Cd_b")
    assert_close(report["Cm_balance"], bal["Cm"], 1e-8, "Cm_b")
    assert_close(report["Cl_delta"], forces["Cl"] - bal["Cl"], 1e-8, "delta")
    assert report["closure_pass"] is True
    assert abs(report["Cl_pressure"] - report["Cl_balance"]) <= float(camp["conditions"]["closure_tol_Cl"])


@pytest.mark.parametrize("name", ["NACA0012-A4", "RAE2822-A2"])
def test_batch_tare_excludes_wind_on(name):
    """Batch tare feature: tare statistics must count only wind_on==false runs."""
    camp = load_campaign(PUBLIC / name)
    tare = reference_tare(camp["tare_runs"]["runs"])
    work = run_validate(PUBLIC / name)
    calib = json.loads((work / "calibration_summary.json").read_text(encoding="utf-8"))
    assert calib["tare_run_count"] == tare["tare_run_count"]
    assert calib["tare_run_count"] == sum(1 for r in camp["tare_runs"]["runs"] if not r["wind_on"])
    assert_close(calib["mean_tare_Fx_N"], tare["mean_tare_Fx_N"], 1e-9)
    assert_close(calib["sigma_tare_Fz_N"], tare["sigma_tare_Fz_N"], 1e-9)
    assert_close(calib["corrected_Fz_N"], reference_balance(camp, tare, reference_q(camp["conditions"]))["corrected_Fz_N"], 1e-8)


@pytest.mark.parametrize("name", ["NACA0012-A4", "RAE2822-A2", "FLATPLATE-A0"])
def test_eval_uncertainty_rss_not_linear(name):
    """Eval uncertainty metric: u_Cl_rss must be RSS of pressure and balance paths, not a linear sum."""
    camp = load_campaign(PUBLIC / name)
    q = reference_q(camp["conditions"])
    pairs = reference_pairs(camp, q)
    forces = reference_forces(pairs, float(camp["conditions"]["alpha_deg"]))
    tare = reference_tare(camp["tare_runs"]["runs"])
    bal = reference_balance(camp, tare, q)
    expect = reference_unc(camp["conditions"], q, pairs, forces, bal)
    work = run_validate(PUBLIC / name)
    unc = json.loads((work / "uncertainty_budget.json").read_text(encoding="utf-8"))
    assert_close(unc["u_q_inf_pa"], expect["u_q_inf_pa"], 1e-8)
    assert_close(unc["u_Cl_pressure"], expect["u_Cl_pressure"], 1e-8)
    assert_close(unc["u_Cl_balance"], expect["u_Cl_balance"], 1e-8)
    assert_close(unc["u_Cl_rss"], expect["u_Cl_rss"], 1e-8)
    linear = expect["u_Cl_pressure"] + expect["u_Cl_balance"]
    assert abs(unc["u_Cl_rss"] - linear) > 1e-12


def test_feature_coefficient_table_schema():
    """Feature/label coefficient_table.csv must use the documented header and pressure/balance row layout."""
    work = run_validate(PUBLIC / "NACA0012-A4")
    rows = list(csv.reader((work / "coefficient_table.csv").open(encoding="utf-8")))
    assert rows[0] == ["path", "Cn", "Ca", "Cl", "Cd", "Cm"]
    assert rows[1][0] == "pressure"
    assert rows[2][0] == "balance"
    assert rows[2][1] == "" and rows[2][2] == ""


def test_eval_report_seal_matches_fnv():
    """Eval report_seal metric bind must match the FNV-1a digest specified in artifact-layout.md."""
    work = run_validate(PUBLIC / "NACA0012-A4")
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    seal = fnv_seal(
        report["campaign_id"],
        report["q_inf_pa"],
        report["Cl_pressure"],
        report["Cd_pressure"],
        report["Cm_pressure"],
        report["Cl_balance"],
    )
    assert report["report_seal"] == seal


def test_metric_s_ref_chord_times_span():
    """Eval metric unit basis: S_ref_m2 must equal chord_m * span_m."""
    camp = load_campaign(PUBLIC / "RAE2822-A2")
    work = run_validate(PUBLIC / "RAE2822-A2")
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    expect = float(camp["conditions"]["chord_m"]) * float(camp["conditions"]["span_m"])
    assert_close(report["S_ref_m2"], expect, 1e-12)


def test_model_quarter_chord_moment():
    """Model inference pitching-moment: Cm must be about xref_c=0.25, not the leading edge."""
    camp = load_campaign(PUBLIC / "NACA0012-A4")
    q = reference_q(camp["conditions"])
    pairs = reference_pairs(camp, q)
    cm_c4 = reference_cm(pairs, 0.25)
    cm_le = reference_cm(pairs, 0.0)
    work = run_validate(PUBLIC / "NACA0012-A4")
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["Cm_pressure"], cm_c4, 1e-8)
    assert abs(report["Cm_pressure"] - cm_le) > 1e-4


def test_model_alpha_zero_drag_equals_ca():
    """Model inference at alpha=0: Cl equals Cn and Cd equals Ca."""
    camp = load_campaign(PUBLIC / "FLATPLATE-A0")
    q = reference_q(camp["conditions"])
    pairs = reference_pairs(camp, q)
    forces = reference_forces(pairs, 0.0)
    work = run_validate(PUBLIC / "FLATPLATE-A0")
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["Cd_pressure"], forces["Ca"], 1e-8)
    assert_close(report["Cl_pressure"], forces["Cn"], 1e-8)


def test_eval_uncertainty_components_named():
    """Eval uncertainty_budget.json metrics components must use the four documented names."""
    work = run_validate(PUBLIC / "NACA0012-A4")
    unc = json.loads((work / "uncertainty_budget.json").read_text(encoding="utf-8"))
    names = [c["name"] for c in unc["components"]]
    assert names == ["dyn_pressure", "pressure_path", "balance_path", "rss_combined"]


def test_feature_decoy_prandtl_not_used():
    """Feature pipeline must not route q_inf through wtac_decoy_prandtl_q."""
    camp = load_campaign(PUBLIC / "NACA0012-A4")
    from wtac.decoy.decoy_prandtl import wtac_decoy_prandtl_q

    q = reference_q(camp["conditions"])
    decoy = wtac_decoy_prandtl_q(q, 0.3)
    work = run_validate(PUBLIC / "NACA0012-A4")
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["q_inf_pa"], q, 1e-9)
    assert abs(report["q_inf_pa"] - decoy) > 1.0


# --- held-out perturbation ---


def _write_heldout(dest: Path, alpha: float, scale: float) -> None:
    """Deterministic held-out campaign derived from public geometry with scaled Cp."""
    base = load_campaign(PUBLIC / "NACA0012-A4")
    cond = dict(base["conditions"])
    cond["campaign_id"] = dest.name
    cond["alpha_deg"] = alpha
    cond["closure_tol_Cl"] = 0.03
    q = reference_q(cond)
    samples = []
    for s in base["pressures"]["samples"]:
        cp = (float(s["p_pa"]) - float(base["conditions"]["p_inf_pa"])) / reference_q(base["conditions"])
        samples.append({"tap_id": s["tap_id"], "p_pa": cond["p_inf_pa"] + scale * cp * q})
    pairs_tmp = []
    # build pairs for force target
    cps = {str(s["tap_id"]): (float(s["p_pa"]) - cond["p_inf_pa"]) / q for s in samples}
    upper, lower = {}, {}
    for tap in base["geometry"]["taps"]:
        key = round(float(tap["x_c"]), 12)
        (upper if tap["surface"] == "upper" else lower)[key] = tap
    for key in sorted(set(upper) & set(lower)):
        u, lo = upper[key], lower[key]
        pairs_tmp.append(
            {
                "x_c": float(u["x_c"]),
                "z_u": float(u["z_c"]),
                "z_l": float(lo["z_c"]),
                "Cp_u": cps[str(u["tap_id"])],
                "Cp_l": cps[str(lo["tap_id"])],
            }
        )
    forces = reference_forces(pairs_tmp, alpha)
    cm = reference_cm(pairs_tmp, float(cond["xref_c"]))
    s_ref = float(cond["chord_m"]) * float(cond["span_m"])
    tare_off = {"Fx": 1.0, "Fz": -0.5, "My": 0.05}
    tare_runs = {
        "runs": [
            {"run_id": "T0", "wind_on": False, "Fx_N": tare_off["Fx"], "Fz_N": tare_off["Fz"], "My_Nm": tare_off["My"]},
            {
                "run_id": "T1",
                "wind_on": False,
                "Fx_N": tare_off["Fx"] + 0.3,
                "Fz_N": tare_off["Fz"] - 0.1,
                "My_Nm": tare_off["My"] + 0.02,
            },
            {
                "run_id": "W1",
                "wind_on": True,
                "Fx_N": 99.0,
                "Fz_N": 99.0,
                "My_Nm": 99.0,
            },
        ]
    }
    mean_fx = (tare_runs["runs"][0]["Fx_N"] + tare_runs["runs"][1]["Fx_N"]) / 2.0
    mean_fz = (tare_runs["runs"][0]["Fz_N"] + tare_runs["runs"][1]["Fz_N"]) / 2.0
    mean_my = (tare_runs["runs"][0]["My_Nm"] + tare_runs["runs"][1]["My_Nm"]) / 2.0
    balance = {
        "Fx_N": forces["Cd"] * q * s_ref + mean_fx,
        "Fz_N": forces["Cl"] * q * s_ref + mean_fz,
        "My_Nm": cm * q * s_ref * float(cond["chord_m"]) + mean_my,
    }
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "conditions.json").write_text(json.dumps(cond, indent=2) + "\n", encoding="utf-8")
    shutil.copy(PUBLIC / "NACA0012-A4" / "geometry.json", dest / "geometry.json")
    (dest / "pressures.json").write_text(json.dumps({"samples": samples}, indent=2) + "\n", encoding="utf-8")
    (dest / "balance.json").write_text(json.dumps(balance, indent=2) + "\n", encoding="utf-8")
    (dest / "tare_runs.json").write_text(json.dumps(tare_runs, indent=2) + "\n", encoding="utf-8")


def test_eval_heldout_campaign_metrics():
    """Eval metrics: held-out HELD-ALPHA campaign must pass closure metric under the same contracts."""
    dest = Path(__file__).resolve().parent / "verifier-fixtures" / "campaigns" / "HELD-ALPHA"
    camp = load_campaign(dest)
    work = run_validate(dest)
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    q = reference_q(camp["conditions"])
    pairs = reference_pairs(camp, q)
    forces = reference_forces(pairs, float(camp["conditions"]["alpha_deg"]))
    assert_close(report["Cl_pressure"], forces["Cl"], 1e-7)
    assert report["closure_pass"] is True
    assert report["campaign_id"] == "HELD-ALPHA"


def test_feature_heldout_differs_from_public():
    """Feature held-out coefficients must differ from the public NACA0012-A4 baseline."""
    dest = Path(__file__).resolve().parent / "verifier-fixtures" / "campaigns" / "HELD-ALPHA"
    pub = run_validate(PUBLIC / "NACA0012-A4")
    held = run_validate(dest)
    a = json.loads((pub / "lift_drag_report.json").read_text(encoding="utf-8"))
    b = json.loads((held / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert abs(a["Cl_pressure"] - b["Cl_pressure"]) > 0.01


def test_eval_heldout_beta_metrics():
    """Eval metrics trap: second held-out campaign under verifier-fixtures must also pass."""
    dest = Path(__file__).resolve().parent / "verifier-fixtures" / "campaigns" / "HELD-BETA"
    camp = load_campaign(dest)
    work = run_validate(dest)
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    q = reference_q(camp["conditions"])
    pairs = reference_pairs(camp, q)
    forces = reference_forces(pairs, float(camp["conditions"]["alpha_deg"]))
    assert_close(report["Cl_pressure"], forces["Cl"], 1e-7)
    assert report["campaign_id"] == "HELD-BETA"
    assert report["closure_pass"] is True


def test_model_perturb_alpha_changes_cl_cd():
    """Model perturbation: changing alpha must change Cl and Cd."""
    d1 = Path(tempfile.mkdtemp()) / "a3"
    d2 = Path(tempfile.mkdtemp()) / "a8"
    _write_heldout(d1, alpha=3.0, scale=1.0)
    _write_heldout(d2, alpha=8.0, scale=1.0)
    r1 = json.loads((run_validate(d1) / "lift_drag_report.json").read_text(encoding="utf-8"))
    r2 = json.loads((run_validate(d2) / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert abs(r1["Cl_pressure"] - r2["Cl_pressure"]) > 1e-4
    assert abs(r1["Cd_pressure"] - r2["Cd_pressure"]) > 1e-6


def test_eval_artifact_files_exist():
    """Eval artifacts: all four required work-dir files must be written."""
    work = run_validate(PUBLIC / "NACA0012-A4")
    for name in (
        "lift_drag_report.json",
        "coefficient_table.csv",
        "calibration_summary.json",
        "uncertainty_budget.json",
    ):
        assert (work / name).is_file()


def test_feature_batch_schema_and_q():
    """Feature staging: feature_batch.json must carry contract keys and correct q_inf/alpha_rad."""
    camp = load_campaign(PUBLIC / "NACA0012-A4")
    work = run_feature(PUBLIC / "NACA0012-A4")
    batch = json.loads((work / "feature_batch.json").read_text(encoding="utf-8"))
    assert set(batch) >= {"campaign_id", "q_inf_pa", "alpha_rad", "pairs", "feature_epoch"}
    q = reference_q(camp["conditions"])
    assert_close(batch["q_inf_pa"], q, 1e-9)
    assert abs(batch["q_inf_pa"] - float(camp["conditions"]["pitot_q_pa"])) > 1.0
    expect_rad = float(camp["conditions"]["alpha_deg"]) * math.pi / 180.0
    assert_close(batch["alpha_rad"], expect_rad, 1e-12)
    assert abs(batch["alpha_rad"] - float(camp["conditions"]["alpha_deg"])) > 0.05
    assert isinstance(batch["pairs"], list) and len(batch["pairs"]) >= 2
    ledger = json.loads((work / "feature_ledger.json").read_text(encoding="utf-8"))
    assert ledger["feature_epoch"] == batch["feature_epoch"]
    assert ledger["feature_epoch"] >= 1


def test_eval_requires_feature_batch():
    """Eval staging: eval without a prior feature staging file must fail nonzero."""
    work = Path(tempfile.mkdtemp(prefix="wtac-missing-"))
    proc = subprocess.run(
        [
            BINARY,
            "eval",
            "--campaign-dir",
            str(PUBLIC / "NACA0012-A4"),
            "--work-dir",
            str(work),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert not (work / "lift_drag_report.json").is_file()


def test_eval_consumes_staged_q_inf():
    """Eval staging poison: mutating staged q_inf after feature must change eval report q_inf."""
    camp_path = PUBLIC / "RAE2822-A2"
    work = run_feature(camp_path)
    batch_path = work / "feature_batch.json"
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    mutated = float(batch["q_inf_pa"]) * 1.17
    batch["q_inf_pa"] = mutated
    batch_path.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_eval(camp_path, work)
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["q_inf_pa"], mutated, 1e-9)


def test_feature_ledger_epoch_monotonic():
    """Feature ledger: a second feature run must bump feature_epoch; eval increments eval_count."""
    camp_path = PUBLIC / "FLATPLATE-A0"
    work = run_feature(camp_path)
    e1 = json.loads((work / "feature_ledger.json").read_text(encoding="utf-8"))["feature_epoch"]
    run_feature(camp_path, work)
    e2 = json.loads((work / "feature_ledger.json").read_text(encoding="utf-8"))["feature_epoch"]
    assert e2 == e1 + 1
    run_eval(camp_path, work)
    ledger = json.loads((work / "feature_ledger.json").read_text(encoding="utf-8"))
    assert ledger["eval_count"] >= 1
    assert ledger["feature_epoch"] == e2


def test_staged_alpha_rad_drives_report_alpha():
    """Eval staging: report alpha_rad must equal staged alpha_rad (radians), not raw degrees."""
    camp = load_campaign(PUBLIC / "NACA0012-A4")
    work = run_validate(PUBLIC / "NACA0012-A4")
    batch = json.loads((work / "feature_batch.json").read_text(encoding="utf-8"))
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["alpha_rad"], batch["alpha_rad"], 1e-12)
    assert_close(report["alpha_rad"], float(camp["conditions"]["alpha_deg"]) * math.pi / 180.0, 1e-12)


def test_feature_decoy_pitot_blend_not_used():
    """Feature pipeline must not route q_inf through wtac_decoy_pitot_blend."""
    camp = load_campaign(PUBLIC / "NACA0012-A4")
    from wtac.decoy.decoy_pitot_blend import wtac_decoy_pitot_blend

    q = reference_q(camp["conditions"])
    blend = wtac_decoy_pitot_blend(q, float(camp["conditions"]["pitot_q_pa"]), 0.4)
    work = run_validate(PUBLIC / "NACA0012-A4")
    report = json.loads((work / "lift_drag_report.json").read_text(encoding="utf-8"))
    assert_close(report["q_inf_pa"], q, 1e-9)
    assert abs(report["q_inf_pa"] - blend) > 1.0
