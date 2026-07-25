"""Verification of the GW-Basin-12 volumetric mass-conservation diagnostics.

Every expected quantity in this module is recomputed from the read-only evidence
set under /app/data using the staged evaluation of the mass-conservation
contract. No expected value is taken from the emitted document, from the scalar
profile, or from any property certificate.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

APP = Path("/app")
DATA = APP / "data"
REPORT = APP / "output" / "water_budget_report.json"

DEPTH_DIVISOR = 1000.0
WILT_HEAD_M = 10.0
FIELD_HEAD_M = 25.0
COOPER_JACOB = 2.303
CLOSURE_TOL = 1e-6


def load_json(path: Path):
    with path.open() as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_fingerprints() -> dict[str, str]:
    return {
        str(p.relative_to(DATA)): sha256_file(p)
        for p in sorted(DATA.rglob("*"))
        if p.is_file()
    }


EVIDENCE_AT_IMPORT = evidence_fingerprints()


def read_dir(sub: str) -> list[dict]:
    return [load_json(p) for p in sorted((DATA / sub).glob("*.json"))]


def mesh_cells() -> dict[str, dict]:
    return {c["cell_id"]: c for c in read_dir("mesh")}


def ols_slope(xs: list[float], ys: list[float]) -> float:
    """Ordinary least-squares slope with an intercept term."""
    n = float(len(xs))
    sx = sum(xs)
    sy = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys, strict=True))
    sxx = sum(x * x for x in xs)
    return (n * sxy - sx * sy) / (n * sxx - sx * sx)


def origin_slope(xs: list[float], ys: list[float]) -> float:
    """Least-squares slope of a strictly proportional relation."""
    sxy = sum(x * y for x, y in zip(xs, ys, strict=True))
    sxx = sum(x * x for x in xs)
    return sxy / sxx


def identified_conductivity() -> dict[str, float]:
    """Stage B: Cooper-Jacob conductivity per cell from admitted drawdown samples."""
    cells = mesh_cells()
    out = {}
    for test in read_dir("aquifer_tests"):
        admitted = [s for s in test["samples"] if s["in_straight_line_window"]]
        xs = [math.log10(s["elapsed_min"]) for s in admitted]
        ys = [s["drawdown_m"] for s in admitted]
        slope = ols_slope(xs, ys)
        transmissivity = COOPER_JACOB * test["discharge_m3_per_d"] / (4.0 * math.pi * slope)
        out[test["cell_id"]] = transmissivity / cells[test["cell_id"]]["sat_thickness_m"]
    return out


def identified_specific_yield() -> dict[str, float]:
    """Stage C: proportional storage-response specific yield per cell."""
    cells = mesh_cells()
    out = {}
    for response in read_dir("storage_response"):
        area = cells[response["cell_id"]]["area_m2"]
        xs = [r["injected_volume_m3"] / area for r in response["records"]]
        ys = [r["head_rise_m"] for r in response["records"]]
        out[response["cell_id"]] = 1.0 / origin_slope(xs, ys)
    return out


def stress_factor(head_start: float, head_end: float) -> float:
    """Stage D: mid-period average-head evapotranspiration stress factor."""
    reference = 0.5 * (head_start + head_end)
    raw = (reference - WILT_HEAD_M) / (FIELD_HEAD_M - WILT_HEAD_M)
    return max(0.0, min(1.0, raw))


def budget_terms(row: dict, cell: dict, k: float, sy: float) -> dict:
    stress = stress_factor(row["head_start_m"], row["head_end_m"])
    return {
        "recharge_driver": (row["precip_mm"] / DEPTH_DIVISOR) * cell["area_m2"],
        "et_driver": (row["pet_mm"] / DEPTH_DIVISOR) * cell["area_m2"] * stress,
        "lateral_m3": k * cell["face_area_m2"] * row["hydraulic_gradient"] * row["period_days"],
        "storage_m3": sy * cell["area_m2"] * (row["head_end_m"] - row["head_start_m"]),
        "stress": stress,
    }


def identified_pair() -> tuple[float, float]:
    """Stage E: recharge efficiency and crop factor by mass-balance inversion."""
    cells = mesh_cells()
    k_map = identified_conductivity()
    sy_map = identified_specific_yield()
    aa = ab = bb = ra = rb = 0.0
    for record in read_dir("calibration"):
        if not record["qualified"]:
            continue
        cell = cells[record["cell_id"]]
        t = budget_terms(record, cell, k_map[record["cell_id"]], sy_map[record["cell_id"]])
        col_a = t["recharge_driver"]
        col_b = -t["et_driver"]
        rhs = record["pump_m3"] + t["storage_m3"] - t["lateral_m3"]
        aa += col_a * col_a
        ab += col_a * col_b
        bb += col_b * col_b
        ra += col_a * rhs
        rb += col_b * rhs
    det = aa * bb - ab * ab
    return (ra * bb - ab * rb) / det, (aa * rb - ra * ab) / det


def expected_periods() -> list[dict]:
    """Stage F: expected period rows in ascending period_id order."""
    cells = mesh_cells()
    k_map = identified_conductivity()
    sy_map = identified_specific_yield()
    eta, crop = identified_pair()
    rows = []
    for obs in read_dir("observations"):
        cell = cells[obs["cell_id"]]
        k = k_map[obs["cell_id"]]
        sy = sy_map[obs["cell_id"]]
        t = budget_terms(obs, cell, k, sy)
        recharge = t["recharge_driver"] * eta
        et = t["et_driver"] * crop
        residual = recharge + t["lateral_m3"] - et - obs["pump_m3"] - t["storage_m3"]
        rows.append({
            "period_id": obs["period_id"],
            "cell_id": obs["cell_id"],
            "period_days": obs["period_days"],
            "head_start_m": obs["head_start_m"],
            "head_end_m": obs["head_end_m"],
            "recharge_m3": recharge,
            "et_m3": et,
            "lateral_m3": t["lateral_m3"],
            "pump_m3": obs["pump_m3"],
            "storage_change_m3": t["storage_m3"],
            "balance_residual_m3": residual,
            "et_stress": t["stress"],
            "k_m_per_d": k,
            "sy": sy,
        })
    rows.sort(key=lambda r: r["period_id"])
    return rows


def report() -> dict:
    assert REPORT.exists(), "missing /app/output/water_budget_report.json"
    return load_json(REPORT)


def close(actual: float, expected: float, rel: float = 1e-9, floor: float = 1e-7) -> bool:
    return abs(actual - expected) <= max(floor, rel * max(abs(expected), abs(actual), 1.0))


def test_evidence_files_unchanged():
    """Every file under /app/data keeps the content it was delivered with."""
    assert evidence_fingerprints() == EVIDENCE_AT_IMPORT


def test_document_identity_fields():
    """The document reports schema_version 1.0 and the basin identifier of the evidence set."""
    data = report()
    assert data["schema_version"] == "1.0"
    assert data["basin_id"] == "GW-Basin-12"


def test_calibration_source_is_profile_path():
    """calibration_source is the absolute path of the scalar profile in force."""
    assert report()["calibration_source"] == "/app/config/basin-profile.toml"


def test_period_ordering_and_count():
    """Periods form a flat array in ascending period_id order with a matching period_count."""
    data = report()
    ids = [p["period_id"] for p in data["periods"]]
    expected_ids = [r["period_id"] for r in expected_periods()]
    assert ids == sorted(ids)
    assert ids == expected_ids
    assert data["summary"]["period_count"] == len(expected_ids)


def test_identified_conductivity_on_period_rows():
    """Each period row reports the Cooper-Jacob conductivity identified for its cell."""
    got = report()["periods"]
    for row, exp in zip(got, expected_periods(), strict=True):
        assert close(row["k_m_per_d"], exp["k_m_per_d"], rel=1e-9, floor=1e-9), row["period_id"]


def test_identified_specific_yield_on_period_rows():
    """Each period row reports the proportional storage-response specific yield of its cell."""
    got = report()["periods"]
    for row, exp in zip(got, expected_periods(), strict=True):
        assert close(row["sy"], exp["sy"], rel=1e-9, floor=1e-12), row["period_id"]


def test_identified_pair_reported_in_summary():
    """Summary recharge_efficiency and crop_factor equal the mass-balance inversion result."""
    eta, crop = identified_pair()
    summary = report()["summary"]
    assert close(summary["recharge_efficiency"], eta, rel=1e-9, floor=1e-9)
    assert close(summary["crop_factor"], crop, rel=1e-9, floor=1e-9)


def test_evapotranspiration_stress_factor():
    """Each period row reports the mid-period average-head stress factor."""
    got = report()["periods"]
    for row, exp in zip(got, expected_periods(), strict=True):
        assert close(row["et_stress"], exp["et_stress"], rel=1e-10, floor=1e-12), row["period_id"]


def test_recharge_and_evapotranspiration_volumes():
    """Recharge and evapotranspiration volumes match the staged evaluation."""
    got = report()["periods"]
    for row, exp in zip(got, expected_periods(), strict=True):
        assert close(row["recharge_m3"], exp["recharge_m3"]), row["period_id"]
        assert close(row["et_m3"], exp["et_m3"]), row["period_id"]


def test_lateral_pump_and_storage_volumes():
    """Lateral exchange, abstraction and full elastic storage volumes match the staged evaluation."""
    got = report()["periods"]
    for row, exp in zip(got, expected_periods(), strict=True):
        assert close(row["lateral_m3"], exp["lateral_m3"]), row["period_id"]
        assert close(row["pump_m3"], exp["pump_m3"]), row["period_id"]
        assert close(row["storage_change_m3"], exp["storage_change_m3"]), row["period_id"]


def test_residual_closure_within_contract_tolerance():
    """Every period residual is within 1e-6 and flagged closure_compliant against that tolerance."""
    data = report()
    for row in data["periods"]:
        assert abs(row["balance_residual_m3"]) <= CLOSURE_TOL, row["period_id"]
        assert row["closure_compliant"] is True, row["period_id"]
    assert data["summary"]["max_balance_residual_m3"] <= CLOSURE_TOL
    assert data["summary"]["periods_compliant"] == data["summary"]["period_count"]


def test_max_residual_is_maximum_absolute_period_residual():
    """max_balance_residual_m3 is the maximum absolute period residual of the document."""
    data = report()
    expected = max(abs(row["balance_residual_m3"]) for row in data["periods"])
    assert close(data["summary"]["max_balance_residual_m3"], expected, floor=1e-9)


def test_summary_totals_are_arithmetic_sums_of_period_rows():
    """Summary flux totals equal the arithmetic sums of the emitted period fields."""
    data = report()
    summary = data["summary"]
    rows = data["periods"]
    for total_key, row_key in (
        ("total_recharge_m3", "recharge_m3"),
        ("total_et_m3", "et_m3"),
        ("total_lateral_m3", "lateral_m3"),
        ("total_pump_m3", "pump_m3"),
        ("total_storage_change_m3", "storage_change_m3"),
    ):
        assert close(summary[total_key], sum(r[row_key] for r in rows)), total_key


def test_summary_totals_match_independent_evaluation():
    """Summary flux totals also equal the sums recomputed from the evidence set."""
    summary = report()["summary"]
    rows = expected_periods()
    for total_key, row_key in (
        ("total_recharge_m3", "recharge_m3"),
        ("total_et_m3", "et_m3"),
        ("total_lateral_m3", "lateral_m3"),
        ("total_pump_m3", "pump_m3"),
        ("total_storage_change_m3", "storage_change_m3"),
    ):
        assert close(summary[total_key], sum(r[row_key] for r in rows)), total_key
