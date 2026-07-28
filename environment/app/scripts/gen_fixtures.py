"""Generate public wind-tunnel campaign fixtures with consistent balance targets."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "campaigns"


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


def integrate(pairs: list[dict], alpha_deg: float, xref: float) -> dict:
    xs = [p["x_c"] for p in pairs]
    dcp = [p["Cp_l"] - p["Cp_u"] for p in pairs]
    su = slopes(xs, [p["z_u"] for p in pairs])
    sl = slopes(xs, [p["z_l"] for p in pairs])
    ax = [pairs[i]["Cp_u"] * su[i] - pairs[i]["Cp_l"] * sl[i] for i in range(len(pairs))]
    cn = trapz(dcp, xs)
    ca = trapz(ax, xs)
    a = alpha_deg * math.pi / 180.0
    cl = cn * math.cos(a) - ca * math.sin(a)
    cd = cn * math.sin(a) + ca * math.cos(a)
    cm = trapz([(p["Cp_l"] - p["Cp_u"]) * (xref - p["x_c"]) for p in pairs], xs)
    return {"Cn": cn, "Ca": ca, "Cl": cl, "Cd": cd, "Cm": cm, "alpha_rad": a}


def write_campaign(name: str, cond: dict, taps: list, cps: dict[str, float], tare_off: dict) -> None:
    q = 0.5 * cond["rho_kg_m3"] * cond["V_mps"] ** 2
    pairs = []
    by_x: dict[float, dict] = {}
    for t in taps:
        by_x.setdefault(round(t["x_c"], 12), {})[t["surface"]] = t
    for key in sorted(by_x):
        u = by_x[key]["upper"]
        lo = by_x[key]["lower"]
        pairs.append(
            {
                "x_c": u["x_c"],
                "z_u": u["z_c"],
                "z_l": lo["z_c"],
                "Cp_u": cps[u["tap_id"]],
                "Cp_l": cps[lo["tap_id"]],
            }
        )
    forces = integrate(pairs, cond["alpha_deg"], cond["xref_c"])
    s_ref = cond["chord_m"] * cond["span_m"]
    # Construct wind-on balance so corrected forces match pressure coeffs exactly
    fx_corr = forces["Cd"] * q * s_ref
    fz_corr = forces["Cl"] * q * s_ref
    my_corr = forces["Cm"] * q * s_ref * cond["chord_m"]
    tare_runs = {
        "runs": [
            {
                "run_id": "T0",
                "wind_on": False,
                "Fx_N": tare_off["Fx"],
                "Fz_N": tare_off["Fz"],
                "My_Nm": tare_off["My"],
            },
            {
                "run_id": "T1",
                "wind_on": False,
                "Fx_N": tare_off["Fx"] + 0.4,
                "Fz_N": tare_off["Fz"] - 0.2,
                "My_Nm": tare_off["My"] + 0.05,
            },
            {
                "run_id": "T2",
                "wind_on": False,
                "Fx_N": tare_off["Fx"] - 0.4,
                "Fz_N": tare_off["Fz"] + 0.2,
                "My_Nm": tare_off["My"] - 0.05,
            },
            {
                "run_id": "W1",
                "wind_on": True,
                "Fx_N": fx_corr + tare_off["Fx"] + 12.0,
                "Fz_N": fz_corr + tare_off["Fz"] + 40.0,
                "My_Nm": my_corr + tare_off["My"] + 3.0,
            },
        ]
    }
    mean_fx = (tare_runs["runs"][0]["Fx_N"] + tare_runs["runs"][1]["Fx_N"] + tare_runs["runs"][2]["Fx_N"]) / 3.0
    mean_fz = (tare_runs["runs"][0]["Fz_N"] + tare_runs["runs"][1]["Fz_N"] + tare_runs["runs"][2]["Fz_N"]) / 3.0
    mean_my = (tare_runs["runs"][0]["My_Nm"] + tare_runs["runs"][1]["My_Nm"] + tare_runs["runs"][2]["My_Nm"]) / 3.0
    balance = {
        "Fx_N": fx_corr + mean_fx,
        "Fz_N": fz_corr + mean_fz,
        "My_Nm": my_corr + mean_my,
    }
    samples = []
    for t in taps:
        cp = cps[t["tap_id"]]
        samples.append({"tap_id": t["tap_id"], "p_pa": cond["p_inf_pa"] + cp * q})

    # Decoy pitot 8% high
    cond = dict(cond)
    cond["pitot_q_pa"] = q * 1.08

    dest = OUT / name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "conditions.json").write_text(json.dumps(cond, indent=2) + "\n", encoding="utf-8")
    (dest / "geometry.json").write_text(json.dumps({"taps": taps}, indent=2) + "\n", encoding="utf-8")
    (dest / "pressures.json").write_text(json.dumps({"samples": samples}, indent=2) + "\n", encoding="utf-8")
    (dest / "balance.json").write_text(json.dumps(balance, indent=2) + "\n", encoding="utf-8")
    (dest / "tare_runs.json").write_text(json.dumps(tare_runs, indent=2) + "\n", encoding="utf-8")


def naca_taps(n: int = 8) -> list[dict]:
    taps = []
    for i in range(n):
        x = i / (n - 1)
        # thin symmetric z envelope
        z = 0.12 * (0.2969 * math.sqrt(max(x, 1e-12)) - 0.1260 * x - 0.3516 * x * x + 0.2843 * x**3 - 0.1015 * x**4)
        taps.append({"tap_id": f"U{i}", "x_c": x, "z_c": z, "surface": "upper"})
        taps.append({"tap_id": f"L{i}", "x_c": x, "z_c": -z, "surface": "lower"})
    return taps


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    taps = naca_taps(9)
    # NACA0012-A4: suction upper, pressure lower
    cps_a4 = {}
    for i in range(9):
        x = i / 8
        cps_a4[f"U{i}"] = -0.8 * math.sin(math.pi * x) - 0.15
        cps_a4[f"L{i}"] = 0.55 * math.sin(math.pi * x) + 0.05
    write_campaign(
        "NACA0012-A4",
        {
            "campaign_id": "NACA0012-A4",
            "rho_kg_m3": 1.225,
            "V_mps": 40.0,
            "p_inf_pa": 101325.0,
            "alpha_deg": 4.0,
            "chord_m": 0.5,
            "span_m": 1.0,
            "xref_c": 0.25,
            "u_rho_kg_m3": 0.005,
            "u_V_mps": 0.08,
            "u_p_pa": 12.0,
            "closure_tol_Cl": 0.02,
        },
        taps,
        cps_a4,
        {"Fx": 2.0, "Fz": -1.5, "My": 0.2},
    )

    taps2 = naca_taps(7)
    cps_a2 = {}
    for i in range(7):
        x = i / 6
        cps_a2[f"U{i}"] = -0.55 * math.sin(math.pi * x) - 0.08
        cps_a2[f"L{i}"] = 0.35 * math.sin(math.pi * x) + 0.12
    write_campaign(
        "RAE2822-A2",
        {
            "campaign_id": "RAE2822-A2",
            "rho_kg_m3": 1.18,
            "V_mps": 55.0,
            "p_inf_pa": 100800.0,
            "alpha_deg": 2.0,
            "chord_m": 0.6,
            "span_m": 0.9,
            "xref_c": 0.25,
            "u_rho_kg_m3": 0.004,
            "u_V_mps": 0.1,
            "u_p_pa": 10.0,
            "closure_tol_Cl": 0.015,
        },
        taps2,
        cps_a2,
        {"Fx": 1.2, "Fz": -0.8, "My": 0.1},
    )

    taps0 = naca_taps(5)
    cps0 = {}
    for i in range(5):
        x = i / 4
        # near symmetric at alpha 0 with tiny camber residual
        cps0[f"U{i}"] = -0.2 * math.sin(math.pi * x)
        cps0[f"L{i}"] = 0.2 * math.sin(math.pi * x)
    write_campaign(
        "FLATPLATE-A0",
        {
            "campaign_id": "FLATPLATE-A0",
            "rho_kg_m3": 1.20,
            "V_mps": 30.0,
            "p_inf_pa": 101000.0,
            "alpha_deg": 0.0,
            "chord_m": 0.4,
            "span_m": 0.8,
            "xref_c": 0.25,
            "u_rho_kg_m3": 0.003,
            "u_V_mps": 0.05,
            "u_p_pa": 8.0,
            "closure_tol_Cl": 0.01,
        },
        taps0,
        cps0,
        {"Fx": 0.5, "Fz": 0.0, "My": 0.0},
    )
    print(f"wrote campaigns under {OUT}")


if __name__ == "__main__":
    main()
