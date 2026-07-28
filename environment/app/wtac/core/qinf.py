from __future__ import annotations

from typing import Any


def wtac_dynamic_pressure(conditions: dict[str, Any]) -> float:
    if "pitot_q_pa" in conditions:
        return float(conditions["pitot_q_pa"])
    rho = float(conditions["rho_kg_m3"])
    v = float(conditions["V_mps"])
    return 0.5 * rho * v * v
