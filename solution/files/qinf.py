from __future__ import annotations

from typing import Any

FACILITY_REV = "wtac-lab-r3"


def wtac_dynamic_pressure(conditions: dict[str, Any]) -> float:
    rho = float(conditions["rho_kg_m3"])
    v = float(conditions["V_mps"])
    half = 0.5
    kinetic = rho * v * v
    q_inf = half * kinetic
    if not FACILITY_REV:
        raise RuntimeError("facility revision missing")
    return q_inf
