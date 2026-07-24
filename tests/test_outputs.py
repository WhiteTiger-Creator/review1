"""Span screening verifier for coarse/fine parity observables."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(os.environ.get("APP_ENV_ROOT", "/app/environment"))
OUT = Path(os.environ.get("BEAM_OUT", "/app/output/span_parity.json"))
KIT = ROOT / "exec" / "kit.sh"


def _rebuild_screen() -> dict:
    if OUT.exists():
        OUT.unlink()
    subprocess.run(["bash", "/app/environment/exec/kit.sh"], check=True)
    return json.loads(OUT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report() -> dict:
    return _rebuild_screen()


def _band_limits() -> tuple[str, float, float, float]:
    text = (ROOT / "docs" / "tol_policy.md").read_text(encoding="utf-8")
    tol_class = "abs_span"
    tol_limit = 0.50
    react_tol = 40.0
    lin_tol = 0.08
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("tol_class "):
            tol_class = s.split(None, 1)[1]
        elif s.startswith("tol_limit "):
            tol_limit = float(s.split(None, 1)[1])
        elif s.startswith("react_tol_limit "):
            react_tol = float(s.split(None, 1)[1])
        elif s.startswith("lin_tol_limit "):
            lin_tol = float(s.split(None, 1)[1])
    return tol_class, tol_limit, react_tol, lin_tol


def _iter_rows(report: dict) -> list[dict]:
    rows: list[dict] = []
    for case in report["cases"]:
        rows.extend(case["rows"])
    return rows


def _point_defl(x: float, length: float, e_mod: float, i_sec: float, a: float, p: float) -> float:
    """Simply-supported point-load deflection at x (downward positive)."""
    b = length - a
    ei = e_mod * i_sec
    if x <= a:
        return p * b * x * (length * length - x * x - b * b) / (6.0 * ei * length)
    return p * a * (length - x) * (length * length - (length - x) * (length - x) - a * a) / (
        6.0 * ei * length
    )


def _analytic_mid(case: dict) -> tuple[float, float, float]:
    length = float(case["length_m"])
    e_mod = float(case["e_pa"])
    i_sec = float(case["i_m4"])
    mid = 0.5 * length
    defl = 0.0
    react_l = 0.0
    react_r = 0.0
    for load in case["loads"]:
        a = float(load["x_m"])
        p = float(load["force_n"])
        defl += _point_defl(mid, length, e_mod, i_sec, a, p)
        react_l += p * (length - a) / length
        react_r += p * a / length
    return abs(defl) * 1000.0, react_l, react_r


def test_screen_defl_gap(report: dict) -> None:
    """Coarse vs fine mid-span deflection residual stays inside published tol_limit."""
    _, lim, _, _ = _band_limits()
    for row in _iter_rows(report):
        assert row["defl_residual"] <= lim


def test_screen_react_left(report: dict) -> None:
    """Coarse vs fine left reaction residual stays inside published react_tol_limit."""
    _, _, react_tol, _ = _band_limits()
    for row in _iter_rows(report):
        assert row["react_l_residual"] <= react_tol


def test_screen_react_right(report: dict) -> None:
    """Coarse vs fine right reaction residual stays inside published react_tol_limit."""
    _, _, react_tol, _ = _band_limits()
    for row in _iter_rows(report):
        assert row["react_r_residual"] <= react_tol


def test_screen_lin_defl(report: dict) -> None:
    """After load doubling, lin_defl_ratio is near 2.0 within lin_tol_limit."""
    _, _, _, lin_tol = _band_limits()
    for row in _iter_rows(report):
        assert abs(row["lin_defl_ratio"] - 2.0) <= lin_tol


def test_screen_lin_react(report: dict) -> None:
    """After load doubling, reactions scale near 2x within react_tol_limit."""
    _, _, react_tol, _ = _band_limits()
    for row in _iter_rows(report):
        assert abs(row["react_l_doubled_n"] - 2.0 * row["react_l_coarse_n"]) <= react_tol
        assert abs(row["react_r_doubled_n"] - 2.0 * row["react_r_coarse_n"]) <= react_tol


def test_screen_rerun_lock(report: dict) -> None:
    """Second identical driver run leaves coarse deflection and reactions unchanged."""
    second = _rebuild_screen()
    a = {(c["case_id"], r["row_id"]): r for c in report["cases"] for r in c["rows"]}
    b = {(c["case_id"], r["row_id"]): r for c in second["cases"] for r in c["rows"]}
    assert a.keys() == b.keys()
    for key in a:
        assert a[key]["defl_coarse_mm"] == b[key]["defl_coarse_mm"]
        assert a[key]["react_l_coarse_n"] == b[key]["react_l_coarse_n"]
        assert a[key]["react_r_coarse_n"] == b[key]["react_r_coarse_n"]


def test_screen_byte_lock(report: dict) -> None:
    """Full span_parity.json matches across two consecutive rebuilds."""
    first = OUT.read_bytes()
    _rebuild_screen()
    second = OUT.read_bytes()
    assert first == second


def test_screen_case_cover(report: dict) -> None:
    """Report includes every bundled case with a single main screening row."""
    case_ids = {c["case_id"] for c in report["cases"]}
    for path in sorted((ROOT / "cases").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["case_id"] in case_ids
        got = next(c for c in report["cases"] if c["case_id"] == data["case_id"])
        assert len(got["rows"]) == 1
        assert got["rows"][0]["row_id"] == "main"


def test_screen_schema(report: dict) -> None:
    """Required observation fields exist; no boolean answer-key suffixes."""
    assert "cases" in report and "tol_class" in report and "tol_limit" in report
    assert "react_tol_limit" in report and "lin_tol_limit" in report and "fold_probe" in report
    need = {
        "row_id",
        "defl_coarse_mm",
        "defl_fine_mm",
        "react_l_coarse_n",
        "react_r_coarse_n",
        "react_l_fine_n",
        "react_r_fine_n",
        "defl_residual",
        "react_l_residual",
        "react_r_residual",
        "defl_doubled_mm",
        "lin_defl_ratio",
        "react_l_doubled_n",
        "react_r_doubled_n",
    }
    forbidden = ("_ok", "_valid", "_passes", "_green")
    for row in _iter_rows(report):
        assert need <= set(row)
        for key in row:
            for sfx in forbidden:
                assert key[-len(sfx) :] != sfx


def test_screen_analytic_fine(report: dict) -> None:
    """Independent analytical oracle agrees with emitted fine fields within tolerances."""
    _, lim, react_tol, _ = _band_limits()
    for path in (ROOT / "cases").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        case = next(c for c in report["cases"] if c["case_id"] == data["case_id"])
        row = case["rows"][0]
        defl_mm, react_l, react_r = _analytic_mid(data)
        assert abs(row["defl_fine_mm"] - defl_mm) <= lim
        assert abs(row["react_l_fine_n"] - react_l) <= react_tol
        assert abs(row["react_r_fine_n"] - react_r) <= react_tol


def test_screen_regen(report: dict) -> None:
    """Deleting output and rebuilding from sources regenerates a valid report."""
    assert OUT.exists()
    OUT.unlink()
    assert not OUT.exists()
    again = _rebuild_screen()
    assert OUT.exists()
    assert again["cases"]


def test_screen_band_echo(report: dict) -> None:
    """Emitted band tokens echo the published limit document."""
    tol_class, tol_limit, react_tol, lin_tol = _band_limits()
    assert report["tol_class"] == tol_class
    assert report["tol_limit"] == tol_limit
    assert report["react_tol_limit"] == react_tol
    assert report["lin_tol_limit"] == lin_tol
    assert report["fold_probe"] == 0.0


def _case_map(report: dict) -> dict[str, dict]:
    return {c["case_id"]: c for c in report["cases"]}


def test_screen_stiff_span(report: dict) -> None:
    """Stiff short-span case stays inside deflection residual band."""
    _, lim, _, _ = _band_limits()
    case = _case_map(report)["c_d"]
    row = case["rows"][0]
    assert row["defl_residual"] <= lim


def test_screen_long_soft(report: dict) -> None:
    """Long soft-span case keeps deflection residual inside band with nonzero mid-span deflection."""
    _, lim, _, _ = _band_limits()
    case = _case_map(report)["c_e"]
    row = case["rows"][0]
    assert row["defl_residual"] <= lim
    assert row["defl_fine_mm"] > 1.0


def test_screen_fine_balance(report: dict) -> None:
    """Fine left+right reactions balance total applied force within react_tol_limit."""
    _, _, react_tol, _ = _band_limits()
    for path in (ROOT / "cases").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        total = sum(float(x["force_n"]) for x in data["loads"])
        case = _case_map(report)[data["case_id"]]
        row = case["rows"][0]
        assert abs(row["react_l_fine_n"] + row["react_r_fine_n"] - total) <= react_tol


def test_screen_defl_sign(report: dict) -> None:
    """Coarse and fine mid-span deflections are positive for every case."""
    for row in _iter_rows(report):
        assert row["defl_coarse_mm"] > 0.0
        assert row["defl_fine_mm"] > 0.0
        assert row["defl_doubled_mm"] > 0.0


def test_screen_offspan(report: dict) -> None:
    """Off-midspan single-load case keeps unequal fine reactions within published bands."""
    _, _, react_tol, _ = _band_limits()
    case = _case_map(report)["c_c"]
    row = case["rows"][0]
    assert abs(row["react_l_fine_n"] - row["react_r_fine_n"]) > react_tol
    assert row["react_l_residual"] <= react_tol
    assert row["react_r_residual"] <= react_tol


def test_screen_dense_asym(report: dict) -> None:
    """Five-load asymmetric span keeps deflection and reaction residuals inside published bands."""
    _, lim, react_tol, _ = _band_limits()
    case = _case_map(report)["c_i"]
    row = case["rows"][0]
    assert row["defl_residual"] <= lim
    assert row["react_l_residual"] <= react_tol
    assert row["react_r_residual"] <= react_tol
    assert abs(row["react_l_fine_n"] - row["react_r_fine_n"]) > react_tol


def test_screen_near_support(report: dict) -> None:
    """Near-support load pair keeps left reaction dominant and residuals inside bands."""
    _, lim, react_tol, _ = _band_limits()
    case = _case_map(report)["c_j"]
    row = case["rows"][0]
    assert row["defl_residual"] <= lim
    assert row["react_l_residual"] <= react_tol
    assert row["react_r_residual"] <= react_tol
    assert row["react_l_fine_n"] > row["react_r_fine_n"]
    assert row["react_l_fine_n"] > 2.0 * row["react_r_fine_n"]


def test_screen_mesh_split(report: dict) -> None:
    """Coarse-vs-fine mesh contrast case stays inside deflection residual with positive mid-span deflection."""
    _, lim, _, lin_tol = _band_limits()
    case = _case_map(report)["c_k"]
    row = case["rows"][0]
    assert row["defl_residual"] <= lim
    assert row["defl_fine_mm"] > 0.5
    assert abs(row["lin_defl_ratio"] - 2.0) <= lin_tol


def test_screen_force_ladder(report: dict) -> None:
    """Stepped four-load ladder keeps load-doubling deflection and reaction linearity inside bands."""
    _, lim, react_tol, lin_tol = _band_limits()
    case = _case_map(report)["c_l"]
    row = case["rows"][0]
    assert row["defl_residual"] <= lim
    assert abs(row["lin_defl_ratio"] - 2.0) <= lin_tol
    assert abs(row["react_l_doubled_n"] - 2.0 * row["react_l_coarse_n"]) <= react_tol
    assert abs(row["react_r_doubled_n"] - 2.0 * row["react_r_coarse_n"]) <= react_tol


def test_screen_irregular(report: dict) -> None:
    """Six-load irregular long-span cluster matches analytical fine reactions and stays inside bands."""
    _, lim, react_tol, _ = _band_limits()
    path = ROOT / "cases" / "c_m.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    case = _case_map(report)["c_m"]
    row = case["rows"][0]
    defl_mm, react_l, react_r = _analytic_mid(data)
    assert row["defl_residual"] <= lim
    assert abs(row["defl_fine_mm"] - defl_mm) <= lim
    assert abs(row["react_l_fine_n"] - react_l) <= react_tol
    assert abs(row["react_r_fine_n"] - react_r) <= react_tol
    assert abs(row["react_l_fine_n"] - row["react_r_fine_n"]) > react_tol


def test_screen_coarse_balance(report: dict) -> None:
    """Coarse left+right reactions balance total applied force within react_tol_limit."""
    _, _, react_tol, _ = _band_limits()
    for path in (ROOT / "cases").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        total = sum(float(x["force_n"]) for x in data["loads"])
        case = _case_map(report)[data["case_id"]]
        row = case["rows"][0]
        assert abs(row["react_l_coarse_n"] + row["react_r_coarse_n"] - total) <= react_tol


def test_screen_station_double(report: dict) -> None:
    """Multi-load doubling keeps mid-span deflection near 2x with stations fixed at case coordinates."""
    _, lim, _, lin_tol = _band_limits()
    for cid in ("c_i", "c_l", "c_m"):
        case = _case_map(report)[cid]
        row = case["rows"][0]
        assert row["defl_residual"] <= lim
        assert abs(row["lin_defl_ratio"] - 2.0) <= lin_tol
        path = ROOT / "cases" / f"{cid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        doubled = {
            **data,
            "loads": [
                {**load, "force_n": float(load["force_n"]) * 2.0} for load in data["loads"]
            ],
        }
        defl_mm, _, _ = _analytic_mid(doubled)
        assert abs(row["defl_doubled_mm"] - defl_mm) <= lim * 3.0


def test_screen_class_token(report: dict) -> None:
    """tol_class token is a non-empty string echoed from the published limit document."""
    tol_class, _, _, _ = _band_limits()
    assert report["tol_class"] == tol_class
    assert isinstance(report["tol_class"], str)
    assert len(report["tol_class"]) >= 3


def test_screen_case_order(report: dict) -> None:
    """Emitted cases follow ascending case_id order."""
    ids = [c["case_id"] for c in report["cases"]]
    assert ids == sorted(ids)
    assert len(ids) >= 13


def test_screen_row_singleton(report: dict) -> None:
    """Every case carries exactly one main screening row."""
    for case in report["cases"]:
        assert len(case["rows"]) == 1
        assert case["rows"][0]["row_id"] == "main"


def test_screen_doubled_positive(report: dict) -> None:
    """Doubled coarse reactions stay positive for every case."""
    for row in _iter_rows(report):
        assert row["react_l_doubled_n"] > 0.0
        assert row["react_r_doubled_n"] > 0.0


def test_screen_lin_floor(report: dict) -> None:
    """Load-doubling ratio stays above 1.5 on every row (anti-collapse floor)."""
    for row in _iter_rows(report):
        assert row["lin_defl_ratio"] > 1.5


def test_screen_residual_formula(report: dict) -> None:
    """Emitted defl_residual equals abs(coarse-fine) mid-span deflection."""
    for row in _iter_rows(report):
        assert abs(row["defl_residual"] - abs(row["defl_coarse_mm"] - row["defl_fine_mm"])) < 1e-9


def test_screen_react_residual_formula(report: dict) -> None:
    """Emitted reaction residuals equal absolute coarse-fine differences."""
    for row in _iter_rows(report):
        assert abs(row["react_l_residual"] - abs(row["react_l_coarse_n"] - row["react_l_fine_n"])) < 1e-9
        assert abs(row["react_r_residual"] - abs(row["react_r_coarse_n"] - row["react_r_fine_n"])) < 1e-9


def test_screen_case_count_floor(report: dict) -> None:
    """Bundled screening emits one case object per JSON fixture."""
    paths = sorted((ROOT / "cases").glob("*.json"))
    assert len(report["cases"]) == len(paths)
    assert len(paths) >= 13
    for path, case in zip(paths, report["cases"], strict=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert case["case_id"] == data["case_id"]
        assert len(case["rows"]) == 1
        assert case["rows"][0]["row_id"] == "main"
        assert case["rows"][0]["defl_fine_mm"] > 0.0
        assert case["rows"][0]["defl_coarse_mm"] > 0.0
