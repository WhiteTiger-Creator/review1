"""Semantic checks for the streaming terrain simulation."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
REPORT = APP / "output" / "field_report.json"
RUNNER = APP / "environment" / "scripts" / "build_and_run.sh"
ENV = APP / "environment"
TOLERANCE = 2.0e-12


def run_profile(flag: str = "") -> dict:
    if REPORT.exists():
        REPORT.unlink()
    command = ["bash", str(RUNNER)]
    if flag:
        command.append(flag)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(REPORT.read_text(encoding="utf-8"))


def _height(x: int, y: int) -> float:
    band = (x * 13 + y * 7 + (x // 16) * 5) % 29
    return 0.25 + band * 0.01


def _load_rain(path: Path) -> list[float]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return [float(row["rainfall"]) for row in rows]


def _simulate(rain_path: Path) -> dict:
    width, height, steps = 128, 96, 4
    tile_w, tile_h = 16, 8
    rains = _load_rain(rain_path)
    sediment = 1.0
    records: list[str] = []
    peak = 0
    tiles_x = (width + tile_w - 1) // tile_w
    tiles_y = (height + tile_h - 1) // tile_h
    runs = []

    for step in range(steps):
        rainfall = rains[step]
        terrain = 0.0
        water = 0.0
        edge = 0.0
        running = 0.0
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                filled = 0
                x0, y0 = tx * tile_w, ty * tile_h
                x1, y1 = min(width, x0 + tile_w), min(height, y0 + tile_h)
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        h = _height(x, y)
                        slope = 0.0001 * ((x + 3 * y) % 11)
                        incoming = rainfall * (1.0 + slope) + running * 0.00001
                        running += incoming
                        terrain += h
                        water += incoming
                        border = x in (0, width - 1) or y in (0, height - 1)
                        if border:
                            edge += incoming * 0.000001
                        filled += 1
                        peak = max(peak, filled)
        line = (
            f"{step}|{terrain:.12f}|{water:.12f}|{sediment:.12f}|{edge:.12f};"
        )
        records.append(line)
        runs.append(
            {
                "step": step,
                "terrain_sum": float(f"{terrain:.12f}"),
                "water_sum": float(f"{water:.12f}"),
                "sediment_sum": float(f"{sediment:.12f}"),
                "edge_export": float(f"{edge:.12f}"),
            }
        )

    digest = hashlib.sha256("".join(records).encode("utf-8")).hexdigest()
    return {
        "grid_width": width,
        "grid_height": height,
        "steps": steps,
        "budget_cells": 4096,
        "peak_cells": peak,
        "initial_sediment": 1.0,
        "final_sediment": sediment,
        "sediment_error": abs(sediment - 1.0),
        "tile_count": tiles_x * tiles_y,
        "reduction_digest": digest,
        "runs": runs,
    }


@pytest.fixture(scope="module")
def primary() -> dict:
    return run_profile()


@pytest.fixture(scope="module")
def expected_primary() -> dict:
    return _simulate(ENV / "data" / "rainfall.csv")


def test_domain_and_tile_coverage(primary: dict, expected_primary: dict) -> None:
    """Published domain dimensions and complete tile coverage stay intact."""
    assert primary["grid_width"] == expected_primary["grid_width"]
    assert primary["grid_height"] == expected_primary["grid_height"]
    assert primary["steps"] == expected_primary["steps"]
    assert primary["budget_cells"] == expected_primary["budget_cells"]
    assert primary["tile_count"] == expected_primary["tile_count"]
    assert primary["tile_count"] == (128 // 16) * (96 // 8)


def test_peak_matches_single_tile_resident_set(
    primary: dict,
    expected_primary: dict,
) -> None:
    """Peak working set equals one full tile, not the whole domain."""
    assert primary["peak_cells"] == expected_primary["peak_cells"] == 128
    assert primary["peak_cells"] <= primary["budget_cells"]


def test_sediment_conserved_across_tile_commits(primary: dict) -> None:
    """Sediment mass survives tile-local observation and commit."""
    assert abs(primary["final_sediment"] - primary["initial_sediment"]) <= TOLERANCE
    assert primary["sediment_error"] <= TOLERANCE
    for row in primary["runs"]:
        assert abs(row["sediment_sum"] - primary["initial_sediment"]) <= TOLERANCE


def test_step_observations_match_independent_stream(
    primary: dict,
    expected_primary: dict,
) -> None:
    """Ordered step totals match the independent tiled stream model."""
    assert [row["step"] for row in primary["runs"]] == [0, 1, 2, 3]
    for actual, expected in zip(primary["runs"], expected_primary["runs"], strict=True):
        assert actual["step"] == expected["step"]
        assert abs(actual["terrain_sum"] - expected["terrain_sum"]) <= TOLERANCE
        assert abs(actual["water_sum"] - expected["water_sum"]) <= 1.0e-9
        assert abs(actual["edge_export"] - expected["edge_export"]) <= 1.0e-9
        assert actual["terrain_sum"] > 0.0
        assert actual["water_sum"] > 0.0
        assert actual["edge_export"] > 0.0


def test_reduction_digest_matches_canonical_records(
    primary: dict,
    expected_primary: dict,
) -> None:
    """Digest is SHA-256 over forward canonical run-record text."""
    assert primary["reduction_digest"] == expected_primary["reduction_digest"]
    assert len(primary["reduction_digest"]) == 64
    assert primary["reduction_digest"] == primary["reduction_digest"].lower()


def test_rainfall_csv_drives_alternate_profile(
    expected_primary: dict,
) -> None:
    """Alternate CSV rainfall changes water while preserving the domain."""
    alternate = run_profile("--alternate")
    expected_alt = _simulate(ENV / "data" / "rainfall_alt.csv")
    assert alternate["grid_width"] == expected_alt["grid_width"]
    assert alternate["tile_count"] == expected_alt["tile_count"]
    assert alternate["peak_cells"] == expected_alt["peak_cells"]
    primary_water = [row["water_sum"] for row in expected_primary["runs"]]
    alternate_water = [row["water_sum"] for row in alternate["runs"]]
    assert alternate_water != primary_water
    for actual, expected in zip(alternate["runs"], expected_alt["runs"], strict=True):
        assert abs(actual["water_sum"] - expected["water_sum"]) <= 1.0e-9
    assert alternate["reduction_digest"] == expected_alt["reduction_digest"]


def test_repeat_identity_is_byte_identical() -> None:
    """Clean rebuilds reproduce identical report bytes."""
    first = run_profile()
    first_bytes = REPORT.read_bytes()
    second = run_profile()
    assert second == first
    assert REPORT.read_bytes() == first_bytes
