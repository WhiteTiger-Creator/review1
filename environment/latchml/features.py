"""Design matrix builder."""
from __future__ import annotations
import math


def base_x(ticks):
    n = len(ticks)
    m = sum(ticks) / n
    mx = max(ticks)
    var = sum((t - m) ** 2 for t in ticks) / max(n - 1, 1)
    return m, mx, math.sqrt(var)


def expand_row(ticks):
    x1, x2, x3 = base_x([float(t) for t in ticks])
    return [1.0, x1, x2, x3, x1 * x1, x2 * x2, x3 * x3]


COL_NAMES = ["intercept", "mean", "max", "std", "mean_sq", "max_sq", "std_sq"]


def build_design(traces, workbook):
    rows = []
    for t in traces:
        rows.append({
            "id": t["id"],
            "cohort": t["cohort"],
            "columns": expand_row(t["ticks"]),
            "target_energy": float(t["target_energy"]),
        })
    return {
        "scheme": "hwml.design/v1",
        "identity": workbook["identity"],
        "column_names": COL_NAMES,
        "rows": rows,
    }


def build_vault(design, source_trace_count):
    return {
        "scheme": "hwml.vault/v1",
        "identity": design.get("identity"),
        "column_names": list(design.get("column_names", [])),
        "rows": list(design.get("rows", [])),
        "source_trace_count": int(source_trace_count),
    }
