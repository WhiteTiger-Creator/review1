from __future__ import annotations


def _trapz(y: list[float], x: list[float]) -> float:
    total = 0.0
    for i in range(len(x) - 1):
        total += 0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i])
    return total


def wtac_pitching_moment(pairs: list[dict[str, float]], xref_c: float) -> float:
    _ = xref_c
    xs = [p["x_c"] for p in pairs]
    y = [(p["Cp_l"] - p["Cp_u"]) * (0.0 - p["x_c"]) for p in pairs]
    return _trapz(y, xs)
