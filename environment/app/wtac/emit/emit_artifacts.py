from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def wtac_report_seal(
    campaign_id: str,
    q_inf: float,
    cl_p: float,
    cd_p: float,
    cm_p: float,
    cl_b: float,
) -> str:
    line = f"{campaign_id}|{q_inf:.8f}|{cl_p:.8f}|{cd_p:.8f}|{cm_p:.8f}|{cl_b:.8f}"
    h = 2166136261
    for byte in (line + "\n").encode("utf-8"):
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"


def wtac_emit_artifacts(
    work_dir: Path,
    conditions: dict[str, Any],
    q_inf: float,
    forces: dict[str, float],
    cm: float,
    balance: dict[str, float],
    tare: dict[str, float],
    unc: dict[str, Any],
) -> None:
    work = Path(work_dir)
    cl_p = float(forces["Cl"])
    cd_p = float(forces["Cd"])
    cl_b = float(balance["Cl"])
    cd_b = float(balance["Cd"])
    cm_b = float(balance["Cm"])
    delta = cl_p - cl_b
    tol = float(conditions["closure_tol_Cl"])
    s_ref = float(conditions["chord_m"]) * float(conditions["span_m"])
    report = {
        "campaign_id": conditions["campaign_id"],
        "q_inf_pa": q_inf,
        "alpha_deg": float(conditions["alpha_deg"]),
        "alpha_rad": float(forces["alpha_rad"]),
        "S_ref_m2": s_ref,
        "Cn": float(forces["Cn"]),
        "Ca": float(forces["Ca"]),
        "Cl_pressure": cl_p,
        "Cd_pressure": cd_p,
        "Cm_pressure": float(cm),
        "Cl_balance": cl_b,
        "Cd_balance": cd_b,
        "Cm_balance": cm_b,
        "Cl_delta": delta,
        "closure_pass": abs(delta) <= tol,
        "report_seal": wtac_report_seal(
            str(conditions["campaign_id"]), q_inf, cl_p, cd_p, float(cm), cl_b
        ),
    }
    (work / "lift_drag_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with (work / "coefficient_table.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "Cn", "Ca", "Cl", "Cd", "Cm"])
        w.writerow(
            [
                "pressure",
                f"{forces['Cn']:.10f}",
                f"{forces['Ca']:.10f}",
                f"{cl_p:.10f}",
                f"{cd_p:.10f}",
                f"{cm:.10f}",
            ]
        )
        w.writerow(
            [
                "balance",
                "",
                "",
                f"{cl_b:.10f}",
                f"{cd_b:.10f}",
                f"{cm_b:.10f}",
            ]
        )

    calib = {
        "tare_run_count": int(tare["tare_run_count"]),
        "mean_tare_Fx_N": tare["mean_tare_Fx_N"],
        "mean_tare_Fz_N": tare["mean_tare_Fz_N"],
        "mean_tare_My_Nm": tare["mean_tare_My_Nm"],
        "sigma_tare_Fx_N": tare["sigma_tare_Fx_N"],
        "sigma_tare_Fz_N": tare["sigma_tare_Fz_N"],
        "sigma_tare_My_Nm": tare["sigma_tare_My_Nm"],
        "corrected_Fx_N": balance["corrected_Fx_N"],
        "corrected_Fz_N": balance["corrected_Fz_N"],
        "corrected_My_Nm": balance["corrected_My_Nm"],
    }
    (work / "calibration_summary.json").write_text(
        json.dumps(calib, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (work / "uncertainty_budget.json").write_text(
        json.dumps(unc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
