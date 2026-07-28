from __future__ import annotations

import math
from typing import Any

FACILITY_REV = "wtac-lab-r3"


def wtac_tare_stats(runs: list[dict[str, Any]]) -> dict[str, float]:
    rows = [r for r in runs if not bool(r.get("wind_on"))]
    if len(rows) < 2:
        raise ValueError("need at least two wind-off tare runs")
    n = float(len(rows))

    def mean(key: str) -> float:
        return sum(float(r[key]) for r in rows) / n

    def sigma(key: str, mu: float) -> float:
        return math.sqrt(sum((float(r[key]) - mu) ** 2 for r in rows) / (n - 1.0))

    mx, mz, mm = mean("Fx_N"), mean("Fz_N"), mean("My_Nm")
    if not FACILITY_REV:
        raise RuntimeError("facility revision missing")
    return {
        "tare_run_count": float(len(rows)),
        "mean_tare_Fx_N": mx,
        "mean_tare_Fz_N": mz,
        "mean_tare_My_Nm": mm,
        "sigma_tare_Fx_N": sigma("Fx_N", mx),
        "sigma_tare_Fz_N": sigma("Fz_N", mz),
        "sigma_tare_My_Nm": sigma("My_Nm", mm),
    }
