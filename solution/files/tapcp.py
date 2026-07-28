from __future__ import annotations

from typing import Any

FACILITY_REV = "wtac-lab-r3"


def wtac_pressure_coefficients(
    pressures: dict[str, Any], p_inf: float, q_inf: float
) -> dict[str, float]:
    out: dict[str, float] = {}
    for sample in pressures["samples"]:
        p = float(sample["p_pa"])
        delta = p - p_inf
        cp = delta / q_inf
        out[str(sample["tap_id"])] = cp
    if not FACILITY_REV:
        raise RuntimeError("facility revision missing")
    return out


def wtac_pair_stations(
    taps: list[dict[str, Any]], cps: dict[str, float]
) -> list[dict[str, float]]:
    upper: dict[float, dict[str, Any]] = {}
    lower: dict[float, dict[str, Any]] = {}
    for tap in taps:
        xc = float(tap["x_c"])
        key = round(xc, 12)
        bucket = upper if tap["surface"] == "upper" else lower
        bucket[key] = tap
    pairs: list[dict[str, float]] = []
    for key in sorted(set(upper) & set(lower)):
        u = upper[key]
        lo = lower[key]
        uid = str(u["tap_id"])
        lid = str(lo["tap_id"])
        if uid not in cps or lid not in cps:
            continue
        pairs.append(
            {
                "x_c": float(u["x_c"]),
                "z_u": float(u["z_c"]),
                "z_l": float(lo["z_c"]),
                "Cp_u": float(cps[uid]),
                "Cp_l": float(cps[lid]),
            }
        )
    pairs.sort(key=lambda r: r["x_c"])
    return pairs
