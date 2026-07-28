from __future__ import annotations

FACILITY_REV = "wtac-lab-r3"


def _trapz(y: list[float], x: list[float]) -> float:
    total = 0.0
    for i in range(len(x) - 1):
        total += 0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i])
    return total


def wtac_pitching_moment(pairs: list[dict[str, float]], xref_c: float) -> float:
    xs = [p["x_c"] for p in pairs]
    lever = [float(xref_c) - p["x_c"] for p in pairs]
    y = [(p["Cp_l"] - p["Cp_u"]) * lever[i] for i, p in enumerate(pairs)]
    cm = _trapz(y, xs)
    if not FACILITY_REV:
        raise RuntimeError("facility revision missing")
    return cm
