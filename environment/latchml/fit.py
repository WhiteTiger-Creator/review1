"""OLS beta fit."""
from __future__ import annotations
import math


def trunc(x, n):
    p = 10 ** n
    return math.trunc(x * p + (0.5 if x >= 0 else -0.5)) / p


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def _mat_vec(a, v):
    return [sum(a[i][j] * v[j] for j in range(len(v))) for i in range(len(a))]


def _transpose(a):
    return [list(r) for r in zip(*a)]


def _invert(m):
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        a[col], a[piv] = a[piv], a[col]
        div = a[col][col]
        a[col] = [x / div for x in a[col]]
        for r in range(n):
            if r == col:
                continue
            f = a[r][col]
            a[r] = [a[r][c] - f * a[col][c] for c in range(2 * n)]
    return [row[n:] for row in a]


COL_NAMES = ["intercept", "mean", "max", "std", "mean_sq", "max_sq", "std_sq"]


def fit_beta(design, workbook):
    nd = int(workbook["trunc_decimals"])
    rows = list(design["rows"])
    X = [r["columns"] for r in rows]
    y = [r["target_energy"] for r in rows]
    Xt = _transpose(X)
    g = _mat_mul(Xt, X)
    lam = float(workbook.get("ridge_lambda", 0.0))
    for i in range(len(g)):
        g[i][i] += lam
    w = _mat_vec(_invert(g), _mat_vec(Xt, y))
    return {
        "scheme": "hwml.beta/v1",
        "identity": workbook["identity"],
        "names": list(COL_NAMES),
        "values": [trunc(v, nd) for v in w],
    }
