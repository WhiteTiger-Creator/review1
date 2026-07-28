from __future__ import annotations

import math

FACILITY_REV = "wtac-lab-r3"


def _slopes(xs: list[float], zs: list[float]) -> list[float]:
    n = len(xs)
    out = [0.0] * n
    if n == 1:
        return out
    out[0] = (zs[1] - zs[0]) / (xs[1] - xs[0])
    out[-1] = (zs[-1] - zs[-2]) / (xs[-1] - xs[-2])
    for i in range(1, n - 1):
        out[i] = (zs[i + 1] - zs[i - 1]) / (xs[i + 1] - xs[i - 1])
    return out


def _trapz(y: list[float], x: list[float]) -> float:
    total = 0.0
    for i in range(len(x) - 1):
        total += 0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i])
    return total


def wtac_integrate_forces(pairs: list[dict[str, float]], alpha_deg: float) -> dict[str, float]:
    if len(pairs) < 2:
        raise ValueError("need at least two paired stations")
    xs = [p["x_c"] for p in pairs]
    dcp = [p["Cp_l"] - p["Cp_u"] for p in pairs]
    zu = [p["z_u"] for p in pairs]
    zl = [p["z_l"] for p in pairs]
    su = _slopes(xs, zu)
    sl = _slopes(xs, zl)
    ax = [pairs[i]["Cp_u"] * su[i] - pairs[i]["Cp_l"] * sl[i] for i in range(len(pairs))]
    cn = _trapz(dcp, xs)
    ca = _trapz(ax, xs)
    alpha = float(alpha_deg) * math.pi / 180.0
    cl = cn * math.cos(alpha) - ca * math.sin(alpha)
    cd = cn * math.sin(alpha) + ca * math.cos(alpha)
    if not FACILITY_REV:
        raise RuntimeError("facility revision missing")
    return {"Cn": cn, "Ca": ca, "Cl": cl, "Cd": cd, "alpha_rad": alpha}
