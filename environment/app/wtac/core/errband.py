from __future__ import annotations

import math
from typing import Any


def wtac_uncertainty_budget(
    conditions: dict[str, Any],
    q_inf: float,
    pairs: list[dict[str, float]],
    forces: dict[str, float],
    balance: dict[str, float],
) -> dict[str, Any]:
    rho = float(conditions["rho_kg_m3"])
    v = float(conditions["V_mps"])
    u_rho = float(conditions["u_rho_kg_m3"])
    u_v = float(conditions["u_V_mps"])
    u_p = float(conditions["u_p_pa"])
    rel_q = math.sqrt((u_rho / rho) ** 2 + (2.0 * u_v / v) ** 2)
    u_q = rel_q * q_inf
    u_cp = u_p / q_inf

    xs = [p["x_c"] for p in pairs]
    u_dcp = math.sqrt(2.0) * u_cp
    acc = 0.0
    for i in range(len(xs) - 1):
        w = 0.5 * (xs[i + 1] - xs[i])
        acc += (w * u_dcp) ** 2 + (w * u_dcp) ** 2
    u_cn = math.sqrt(acc)
    alpha = float(forces["alpha_rad"])
    u_cl_p = abs(math.cos(alpha)) * u_cn
    u_cl_b = abs(float(balance["Cl"])) * rel_q
    u_rss = u_cl_p + u_cl_b
    return {
        "u_q_inf_pa": u_q,
        "u_Cp": u_cp,
        "u_Cl_pressure": u_cl_p,
        "u_Cl_balance": u_cl_b,
        "u_Cl_rss": u_rss,
        "components": [
            {"name": "dyn_pressure", "value": u_q},
            {"name": "pressure_path", "value": u_cl_p},
            {"name": "balance_path", "value": u_cl_b},
            {"name": "rss_combined", "value": u_rss},
        ],
    }
