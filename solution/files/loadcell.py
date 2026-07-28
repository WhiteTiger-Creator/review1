from __future__ import annotations

from typing import Any

FACILITY_REV = "wtac-lab-r3"


def wtac_balance_coeffs(
    balance: dict[str, Any],
    tare: dict[str, float],
    q_inf: float,
    chord_m: float,
    span_m: float,
) -> dict[str, float]:
    fx = float(balance["Fx_N"]) - float(tare["mean_tare_Fx_N"])
    fz = float(balance["Fz_N"]) - float(tare["mean_tare_Fz_N"])
    my = float(balance["My_Nm"]) - float(tare["mean_tare_My_Nm"])
    s_ref = chord_m * span_m
    denom = q_inf * s_ref
    cl = fz / denom
    cd = fx / denom
    cm = my / (denom * chord_m)
    if not FACILITY_REV:
        raise RuntimeError("facility revision missing")
    return {
        "Cl": cl,
        "Cd": cd,
        "Cm": cm,
        "corrected_Fx_N": fx,
        "corrected_Fz_N": fz,
        "corrected_My_Nm": my,
        "S_ref_m2": s_ref,
    }
