"""Schema-8 satcom aperture desk verifier — behavioral subprocess checks only."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

TOOL = Path("/app/bin/pabcal")
LIVE_DESK = Path("/app/config/cal_policy.toml")
SAMPLE = Path("/app/data/sample_array.csv")
JOURNAL = Path("/app/data/desk_journal.csv")
SHA_FILE = Path("/app/data/sealed/production_policy.sha256")

DESK: dict[str, Any] = {
    "schema_version": 8,
    "phase_tol_rad": 0.15,
    "gain_tol_db": 1.5,
    "freq_match_eps_hz": 2.5,
    "freq_anchor": "hinge",
    "c_mps": 299792458.0,
    "steer_az_deg": 25.0,
    "steer_el_deg": 10.0,
    "el_law": "cos_el",
    "norm_mode": "unit_peak",
    "ref_antenna_id": "A00",
    "wrap_half_open": 1,
    "wrap_compose": "wrap_each_then_sum",
    "phase_sign": -1,
    "geo_sign": -1,
    "amp_law": "voltage",
    "mutual_alpha": 0.35,
    "neighbor_radius_m": 0.018,
    "mutual_kernel": "gaussian",
    "couple_mask": "dual_inliers",
    "taper_beta": 0.85,
    "taper_origin": "ref",
    "ref_phase_align": 1,
    "align_mode": "div_ref",
    "outlier_mode": "union_then_cluster",
    "cluster_metric": "chebyshev",
    "cluster_phase_scale": 0.5,
    "cluster_gain_scale": 0.4,
    "rms_basis": "all",
    "digest_bind": "schema_taper_couple_w",
    "policy_revision": "desk-2026.10",
}

REPORT_KEYS = [
    "schema_version",
    "policy_revision",
    "antenna_count",
    "outlier_count",
    "cluster_extra_count",
    "rms_phase_err_rad",
    "max_gain_dev_db",
    "outlier_ids",
    "cal_digest",
    "steer_az_deg",
    "steer_el_deg",
    "norm_mode",
    "ref_antenna_id",
    "ref_phase_align",
    "amp_law",
    "wrap_compose",
]

WEIGHT_COLS = [
    "antenna_id",
    "x_m",
    "y_m",
    "freq_hz",
    "delta_phase_rad",
    "amp_linear",
    "couple",
    "taper",
    "steer_phase_rad",
    "w_real",
    "w_imag",
    "exceeds_tol",
]


POLICY_ORDER = list(DESK.keys())
INT_KEYS = {
    "schema_version",
    "wrap_half_open",
    "phase_sign",
    "geo_sign",
    "ref_phase_align",
}
STR_KEYS = {
    "freq_anchor",
    "el_law",
    "norm_mode",
    "ref_antenna_id",
    "wrap_compose",
    "amp_law",
    "mutual_kernel",
    "couple_mask",
    "taper_origin",
    "align_mode",
    "outlier_mode",
    "cluster_metric",
    "rms_basis",
    "digest_bind",
    "policy_revision",
}


def _desk_midmean(vals: list[float]) -> float:
    if len(vals) < 3:
        s = sorted(vals)
        n = len(s)
        return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
    s = sorted(vals)
    return sum(s[1:-1]) / (len(s) - 2)


def _desk_ceil_mean(vals: list[float]) -> int:
    m = sum(vals) / len(vals)
    return math.ceil(m - 1e-15)


def _desk_fmt_float(x: float) -> str:
    if abs(x - round(x)) < 1e-12 and abs(x) < 1e15:
        return f"{float(round(x)):.1f}"
    s = f"{x:.10f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s


def derive_live_desk_text(journal: Path = JOURNAL) -> str:
    # Independently rebuild cal_policy.toml bytes from the desk journal.
    kept: dict[str, list[str]] = {k: [] for k in POLICY_ORDER}
    jtext = journal.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    first = True
    for raw in jtext.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if first:
            first = False
            continue
        field, vote, token = [part.strip() for part in raw.split(",", 2)]
        if vote != "yes":
            continue
        assert field in kept
        kept[field].append(token)
    lines: list[str] = []
    for key in POLICY_ORDER:
        toks = kept[key]
        assert toks, key
        if key in INT_KEYS:
            v = _desk_ceil_mean([float(t) for t in toks])
            lines.append(f"{key} = {v}")
        elif key in STR_KEYS:
            best = min(toks, key=lambda s: (len(s), s))
            lines.append(f'{key} = "{best}"')
        else:
            v = _desk_midmean([float(t) for t in toks])
            lines.append(f"{key} = {_desk_fmt_float(v)}")
    return "\n".join(lines) + "\n"


def _toml(pol: dict[str, Any]) -> str:
    lines: list[str] = []
    for k, v in pol.items():
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        else:
            lines.append(f"{k} = {v}")
    return "\n".join(lines) + "\n"


def _f10(x: float) -> str:
    if x == 0.0:
        x = 0.0
    return f"{x:.10f}"


def _wrap(x: float, half_open: int) -> float:
    two_pi = 2.0 * math.pi
    y = x
    if half_open == 1:
        while y > math.pi:
            y -= two_pi
        while y <= -math.pi:
            y += two_pi
    else:
        while y >= math.pi:
            y -= two_pi
        while y < -math.pi:
            y += two_pi
    return y


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def _midmean(vals: list[float]) -> float:
    if len(vals) < 3:
        return _median(vals)
    s = sorted(vals)
    return sum(s[1:-1]) / (len(s) - 2)


def _hinge(vals: list[float]) -> float:
    n = len(vals)
    if n < 4:
        return _median(vals)
    s = sorted(vals)
    lo = s[math.floor((n - 1) / 4)]
    hi = s[math.ceil(3 * (n - 1) / 4)]
    return 0.5 * (lo + hi)


def _freq_star(rows: list[dict[str, Any]], pol: dict[str, Any]) -> float:
    freqs = [float(r["freq_hz"]) for r in rows]
    a = pol["freq_anchor"]
    if a == "first":
        return freqs[0]
    if a == "median":
        return _median(freqs)
    if a == "midmean":
        return _midmean(freqs)
    return _hinge(freqs)


def _read_lattice(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    first = True
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in raw.split(",")]
        if first:
            first = False
            continue
        rows.append(
            {
                "antenna_id": parts[0],
                "x_m": float(parts[1]),
                "y_m": float(parts[2]),
                "freq_hz": float(parts[3]),
                "phase_meas_rad": float(parts[4]),
                "gain_err_db": float(parts[5]),
                "ref_phase_rad": float(parts[6]),
            }
        )
    return rows


def _amp(gain_db: float, law: str) -> float:
    if law == "power":
        return 10.0 ** (-gain_db / 10.0)
    return 10.0 ** (-gain_db / 20.0)


def _couple(
    i: int,
    rows: list[dict[str, Any]],
    deltas: list[float],
    pol: dict[str, Any],
) -> float:
    xi, yi = rows[i]["x_m"], rows[i]["y_m"]
    r = float(pol["neighbor_radius_m"])
    s = 0.0
    for j, row in enumerate(rows):
        if j == i:
            continue
        mask = pol["couple_mask"]
        if mask == "gain_inliers" and abs(row["gain_err_db"]) > float(pol["gain_tol_db"]):
            continue
        if mask == "dual_inliers" and (
            abs(row["gain_err_db"]) > float(pol["gain_tol_db"])
            or abs(deltas[j]) > float(pol["phase_tol_rad"])
        ):
            continue
        d = math.hypot(xi - row["x_m"], yi - row["y_m"])
        if d <= r:
            u = d / r
            k = pol["mutual_kernel"]
            if k == "quadratic":
                s += u * u
            elif k == "gaussian":
                s += 1.0 - math.exp(-u * u)
            else:
                s += u
    return math.exp(-float(pol["mutual_alpha"]) * s)


def _origin(rows: list[dict[str, Any]], pol: dict[str, Any]) -> tuple[float, float]:
    if pol["taper_origin"] == "ref":
        for row in rows:
            if row["antenna_id"] == pol["ref_antenna_id"]:
                return row["x_m"], row["y_m"]
        raise AssertionError("ref missing")
    n = len(rows)
    return sum(r["x_m"] for r in rows) / n, sum(r["y_m"] for r in rows) / n


def _taper(x: float, y: float, ox: float, oy: float, pol: dict[str, Any]) -> float:
    r = float(pol["neighbor_radius_m"])
    rho = math.hypot(x - ox, y - oy) / r
    return math.exp(-float(pol["taper_beta"]) * rho * rho)


def _geo(x: float, y: float, freq: float, pol: dict[str, Any]) -> float:
    k = 2.0 * math.pi * freq / float(pol["c_mps"])
    az = float(pol["steer_az_deg"]) * math.pi / 180.0
    el = float(pol["steer_el_deg"]) * math.pi / 180.0
    el_factor = math.cos(el) if pol["el_law"] == "cos_el" else 1.0
    raw = -k * (x * math.sin(az) * el_factor + y * math.sin(el))
    return float(pol["geo_sign"]) * raw


def _compose(delta: float, geo: float, pol: dict[str, Any]) -> float:
    wrap = int(pol["wrap_half_open"])
    resid = float(pol["phase_sign"]) * delta
    if pol["wrap_compose"] == "wrap_each_then_sum":
        return _wrap(resid, wrap) + _wrap(geo, wrap)
    return _wrap(resid + geo, wrap)


def _near(xp: float, yp: float, xq: float, yq: float, r: float, metric: str) -> bool:
    dx, dy = abs(xp - xq), abs(yp - yq)
    if metric == "chebyshev":
        return max(dx, dy) <= r
    return math.hypot(dx, dy) <= r


def expect_desk(rows: list[dict[str, Any]], pol: dict[str, Any]) -> dict[str, Any]:
    wrap = int(pol["wrap_half_open"])
    deltas = [_wrap(r["phase_meas_rad"] - r["ref_phase_rad"], wrap) for r in rows]
    ox, oy = _origin(rows, pol)
    elems: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        delta = deltas[i]
        amp = _amp(row["gain_err_db"], pol["amp_law"])
        couple = _couple(i, rows, deltas, pol)
        taper = _taper(row["x_m"], row["y_m"], ox, oy, pol)
        amp_eff = amp * couple * taper
        phi = _compose(delta, _geo(row["x_m"], row["y_m"], row["freq_hz"], pol), pol)
        elems.append(
            {
                "antenna_id": row["antenna_id"],
                "x_m": row["x_m"],
                "y_m": row["y_m"],
                "freq_hz": row["freq_hz"],
                "delta_phase_rad": delta,
                "amp_linear": amp,
                "couple": couple,
                "taper": taper,
                "steer_phase_rad": phi,
                "w_real": amp_eff * math.cos(phi),
                "w_imag": amp_eff * math.sin(phi),
                "gain_err_db": row["gain_err_db"],
                "primary": False,
                "exceeds_tol": False,
            }
        )

    if int(pol["ref_phase_align"]) == 1:
        ref = next(e for e in elems if e["antenna_id"] == pol["ref_antenna_id"])
        wr, wi = ref["w_real"], ref["w_imag"]
        if pol["align_mode"] == "div_ref":
            if math.hypot(wr, wi) > 0.0:
                denom = wr * wr + wi * wi
                for e in elems:
                    a, b = e["w_real"], e["w_imag"]
                    e["w_real"] = (a * wr + b * wi) / denom
                    e["w_imag"] = (b * wr - a * wi) / denom
        else:
            theta = math.atan2(wi, wr)
            c, s = math.cos(-theta), math.sin(-theta)
            for e in elems:
                a, b = e["w_real"], e["w_imag"]
                e["w_real"] = a * c - b * s
                e["w_imag"] = a * s + b * c

    mode = pol["norm_mode"]
    if mode != "none":
        mags = [math.hypot(e["w_real"], e["w_imag"]) for e in elems]
        denom = max(mags) if mode == "unit_peak" else math.sqrt(sum(m * m for m in mags))
        if denom != 0.0:
            for e in elems:
                e["w_real"] /= denom
                e["w_imag"] /= denom

    pt = float(pol["phase_tol_rad"])
    gt = float(pol["gain_tol_db"])
    for e in elems:
        primary = abs(e["delta_phase_rad"]) > pt or abs(e["gain_err_db"]) > gt
        e["primary"] = primary
        e["exceeds_tol"] = primary

    if pol["outlier_mode"] == "union_then_cluster":
        pth = pt * float(pol["cluster_phase_scale"])
        gth = gt * float(pol["cluster_gain_scale"])
        r = float(pol["neighbor_radius_m"])
        metric = pol["cluster_metric"]
        prim = [e for e in elems if e["primary"]]
        for p in prim:
            for q in elems:
                if q is p:
                    continue
                if (
                    _near(p["x_m"], p["y_m"], q["x_m"], q["y_m"], r, metric)
                    and abs(q["delta_phase_rad"]) > pth
                    and abs(q["gain_err_db"]) > gth
                ):
                    q["exceeds_tol"] = True

    elems.sort(key=lambda e: e["antenna_id"])
    if pol["rms_basis"] == "inliers":
        vals = [e["delta_phase_rad"] for e in elems if not e["exceeds_tol"]]
        rms = 0.0 if not vals else math.sqrt(sum(v * v for v in vals) / len(vals))
    else:
        rms = math.sqrt(sum(e["delta_phase_rad"] ** 2 for e in elems) / len(elems))
    maxg = max(abs(e["gain_err_db"]) for e in elems)
    outs = [e["antenna_id"] for e in elems if e["exceeds_tol"]]
    extra = sum(1 for e in elems if e["exceeds_tol"] and not e["primary"])

    parts = [f"rev:{pol['policy_revision']}"]
    if pol["digest_bind"] == "schema_taper_couple_w":
        parts.append(f"schema:{pol['schema_version']}")
    bind = pol["digest_bind"]
    for e in elems:
        if bind == "weights":
            parts.append(f"{e['antenna_id']}:{_f10(e['w_real'])}:{_f10(e['w_imag'])}")
        elif bind == "couple_weights":
            parts.append(
                f"{e['antenna_id']}:{_f10(e['couple'])}:{_f10(e['w_real'])}:{_f10(e['w_imag'])}"
            )
        else:
            parts.append(
                f"{e['antenna_id']}:{_f10(e['taper'])}:{_f10(e['couple'])}:{_f10(e['w_real'])}:{_f10(e['w_imag'])}"
            )
    parts.append(f"rms:{_f10(rms)}:maxg:{_f10(maxg)}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return {
        "elems": elems,
        "rms": rms,
        "maxg": maxg,
        "outlier_ids": outs,
        "cluster_extra_count": extra,
        "cal_digest": digest,
        "exit": 0 if len(outs) == 0 else 1,
    }


def _run(
    lattice: Path,
    desk: Path,
    weights: Path,
    report: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(TOOL),
            "--lattice",
            str(lattice),
            "--desk",
            str(desk),
            "--weights",
            str(weights),
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_lattice(path: Path, rows: list[dict[str, Any]]) -> None:
    hdr = "antenna_id,x_m,y_m,freq_hz,phase_meas_rad,gain_err_db,ref_phase_rad"
    lines = [hdr]
    for r in rows:
        lines.append(
            ",".join(
                [
                    str(r["antenna_id"]),
                    str(r["x_m"]),
                    str(r["y_m"]),
                    str(r["freq_hz"]),
                    str(r["phase_meas_rad"]),
                    str(r["gain_err_db"]),
                    str(r["ref_phase_rad"]),
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _assert_pack(
    tmp: Path,
    rows: list[dict[str, Any]],
    pol: dict[str, Any] | None = None,
    expect_rc: int | None = None,
) -> dict[str, Any]:
    policy = dict(DESK if pol is None else pol)
    tmp.mkdir(parents=True, exist_ok=True)
    desk = tmp / "desk.toml"
    lat = tmp / "lattice.csv"
    weights = tmp / "weights.csv"
    report = tmp / "report.json"
    desk.write_text(_toml(policy), encoding="utf-8")
    _write_lattice(lat, rows)
    exp = expect_desk(rows, policy)
    want = exp["exit"] if expect_rc is None else expect_rc
    proc = _run(lat, desk, weights, report)
    assert proc.returncode == want, proc.stderr
    assert proc.stdout == ""
    got_rows = list(csv.DictReader(weights.open(encoding="utf-8")))
    assert list(got_rows[0].keys()) == WEIGHT_COLS
    assert len(got_rows) == len(exp["elems"])
    for got, want_e in zip(got_rows, exp["elems"], strict=True):
        assert got["antenna_id"] == want_e["antenna_id"]
        assert abs(float(got["delta_phase_rad"]) - want_e["delta_phase_rad"]) < 1e-9
        assert abs(float(got["amp_linear"]) - want_e["amp_linear"]) < 1e-9
        assert abs(float(got["couple"]) - want_e["couple"]) < 1e-9
        assert abs(float(got["taper"]) - want_e["taper"]) < 1e-9
        assert abs(float(got["steer_phase_rad"]) - want_e["steer_phase_rad"]) < 1e-9
        assert abs(float(got["w_real"]) - want_e["w_real"]) < 1e-9
        assert abs(float(got["w_imag"]) - want_e["w_imag"]) < 1e-9
        assert got["exceeds_tol"] == ("true" if want_e["exceeds_tol"] else "false")
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert list(rep.keys()) == REPORT_KEYS
    assert rep["schema_version"] == policy["schema_version"]
    assert rep["amp_law"] == policy["amp_law"]
    assert rep["wrap_compose"] == policy["wrap_compose"]
    assert rep["cal_digest"] == exp["cal_digest"]
    assert rep["outlier_ids"] == exp["outlier_ids"]
    assert rep["cluster_extra_count"] == exp["cluster_extra_count"]
    assert abs(rep["rms_phase_err_rad"] - exp["rms"]) < 1e-12
    return exp



def test_journal_midmean_beats_plain_mean_for_floats() -> None:
    """Float desk keys must use midmean of yes-votes, not the arithmetic mean of all yes tokens."""
    derived = derive_live_desk_text()
    assert "phase_tol_rad = 0.15" in derived
    toks: list[float] = []
    first = True
    for raw in JOURNAL.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if first:
            first = False
            continue
        field, vote, token = [part.strip() for part in raw.split(",", 2)]
        if field == "phase_tol_rad" and vote == "yes":
            toks.append(float(token))
    assert abs(sum(toks) / len(toks) - 0.15) > 1e-6


def test_journal_int_uses_ceil_of_mean() -> None:
    """Integer desk keys must ceil the mean of yes-votes (not round-to-nearest)."""
    derived = derive_live_desk_text()
    assert "wrap_half_open = 1" in derived
    assert "schema_version = 8" in derived


def test_journal_string_picks_shortest_token() -> None:
    """String desk keys take the shortest yes-token (lexicographic tie-break)."""
    derived = derive_live_desk_text()
    line = next(ln for ln in derived.splitlines() if ln.startswith("freq_anchor"))
    assert line == 'freq_anchor = "hinge"'


def test_pabcal_binary_is_executable() -> None:
    """Confirm /app/bin/pabcal exists as an executable file."""
    assert TOOL.is_file()
    assert TOOL.stat().st_mode & 0o111


def test_live_desk_fingerprint_matches_journal_sha() -> None:
    """Live desk toml SHA-256 must equal the sealed fingerprint after journal rebuild."""
    got = hashlib.sha256(LIVE_DESK.read_bytes()).hexdigest()
    want = SHA_FILE.read_text(encoding="utf-8").strip()
    assert got == want
    derived = derive_live_desk_text()
    assert hashlib.sha256(derived.encode()).hexdigest() == want
    assert LIVE_DESK.read_text(encoding="utf-8") == derived


def test_default_lattice_emits_schema8_pack(tmp_path: Path) -> None:
    """Sample lattice under sealed desk constants yields schema-8 report and matching digest."""
    rows = _read_lattice(SAMPLE)
    assert all(abs(r["freq_hz"] - _freq_star(rows, DESK)) <= DESK["freq_match_eps_hz"] for r in rows)
    weights = tmp_path / "weights_table.csv"
    report = tmp_path / "desk_summary.json"
    exp = expect_desk(rows, DESK)
    proc = _run(SAMPLE, LIVE_DESK, weights, report)
    assert proc.returncode == exp["exit"]
    assert proc.stdout == ""
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["schema_version"] == 8
    assert rep["cal_digest"] == exp["cal_digest"]
    assert rep["policy_revision"] == "desk-2026.10"
    assert rep["amp_law"] == "voltage"
    assert rep["wrap_compose"] == "wrap_each_then_sum"


def test_default_lattice_exit_one_when_outliers(tmp_path: Path) -> None:
    """Shipped sample under desk policy is valid but still reports outliers (exit 1)."""
    rows = _read_lattice(SAMPLE)
    exp = expect_desk(rows, DESK)
    assert exp["exit"] == 1
    weights = tmp_path / "w.csv"
    report = tmp_path / "r.json"
    proc = _run(SAMPLE, LIVE_DESK, weights, report)
    assert proc.returncode == 1
    assert weights.is_file() and report.is_file()


def test_amp_law_voltage_uses_divisor_twenty(tmp_path: Path) -> None:
    """amp_law=voltage must use decade divisor 20, not the power-law divisor 10."""
    rows = [
        {
            "antenna_id": "V0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 6.020599913279624,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "V1",
            "x_m": 0.05,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_antenna_id": "V0",
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
            "amp_law": "voltage",
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    ref = next(e for e in exp["elems"] if e["antenna_id"] == "V0")
    assert abs(ref["amp_linear"] - 0.5) < 1e-9


def test_mutual_gaussian_accumulates_one_minus_exp(tmp_path: Path) -> None:
    """mutual_kernel=gaussian must accumulate 1-exp(-u^2), not u^2."""
    rows = [
        {
            "antenna_id": "G0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "G1",
            "x_m": 0.01,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "neighbor_radius_m": 0.02,
            "mutual_alpha": 1.0,
            "mutual_kernel": "gaussian",
            "couple_mask": "all",
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_antenna_id": "G0",
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    g0 = next(e for e in exp["elems"] if e["antenna_id"] == "G0")
    u = 0.01 / 0.02
    want = math.exp(-1.0 * (1.0 - math.exp(-u * u)))
    assert abs(g0["couple"] - want) < 1e-12


def test_couple_mask_dual_inliers_both_gates(tmp_path: Path) -> None:
    """couple_mask=dual_inliers drops neighbors failing either residual or gain gate."""
    rows = [
        {
            "antenna_id": "D0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "D1",
            "x_m": 0.01,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.5,
            "gain_err_db": 0.1,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "D2",
            "x_m": 0.0,
            "y_m": 0.01,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.01,
            "gain_err_db": 0.2,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "neighbor_radius_m": 0.02,
            "mutual_alpha": 1.0,
            "mutual_kernel": "linear",
            "couple_mask": "dual_inliers",
            "phase_tol_rad": 0.15,
            "gain_tol_db": 1.5,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_antenna_id": "D0",
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    d0 = next(e for e in exp["elems"] if e["antenna_id"] == "D0")
    # D1 fails phase gate; only D2 contributes
    assert abs(d0["couple"] - math.exp(-1.0 * (0.01 / 0.02))) < 1e-12


def test_spatial_taper_origin_is_reference_element(tmp_path: Path) -> None:
    """taper_origin=ref must measure rho from the reference element, not the centroid."""
    rows = [
        {
            "antenna_id": "T0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "T1",
            "x_m": 0.03,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "T2",
            "x_m": 0.06,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "taper_origin": "ref",
            "ref_antenna_id": "T0",
            "taper_beta": 1.0,
            "neighbor_radius_m": 0.03,
            "mutual_alpha": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    t2 = next(e for e in exp["elems"] if e["antenna_id"] == "T2")
    assert abs(t2["taper"] - math.exp(-4.0)) < 1e-12


def test_cal_digest_embeds_schema_line_when_bound(tmp_path: Path) -> None:
    """schema_taper_couple_w digest must embed a schema:<n> line after the revision line."""
    rows = [
        {
            "antenna_id": "S0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.01,
            "gain_err_db": 0.1,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "S1",
            "x_m": 0.02,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.02,
            "gain_err_db": -0.1,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "digest_bind": "schema_taper_couple_w",
            "ref_antenna_id": "S0",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
            "outlier_mode": "union",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_phase_align": 0,
            "norm_mode": "none",
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    # Without schema line the digest would differ
    pol2 = dict(pol)
    pol2["digest_bind"] = "taper_couple_weights"
    other = expect_desk(rows, pol2)["cal_digest"]
    assert exp["cal_digest"] != other


def test_outlier_cluster_requires_dual_scaled_gates(tmp_path: Path) -> None:
    """Cluster expansion marks a neighbor only when both scaled phase and gain gates fire."""
    rows = [
        {
            "antenna_id": "P0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 1.0,
            "gain_err_db": 5.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "P1",
            "x_m": 0.01,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.12,
            "gain_err_db": 0.1,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "P2",
            "x_m": 0.0,
            "y_m": 0.01,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.12,
            "gain_err_db": 1.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "phase_tol_rad": 0.2,
            "gain_tol_db": 1.5,
            "cluster_phase_scale": 0.5,
            "cluster_gain_scale": 0.4,
            "neighbor_radius_m": 0.02,
            "cluster_metric": "chebyshev",
            "outlier_mode": "union_then_cluster",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_antenna_id": "P1",
            "ref_phase_align": 0,
            "norm_mode": "none",
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    assert "P0" in exp["outlier_ids"]
    assert "P1" not in exp["outlier_ids"]
    assert "P2" in exp["outlier_ids"]
    assert exp["cluster_extra_count"] == 1


def test_freq_anchor_hinge_rejects_midmean_eps(tmp_path: Path) -> None:
    """freq_anchor=hinge must use Tukey hinges; this pack admits under hinge but not midmean."""
    vals = [1.0, 2.0, 10.0, 20.0, 30.0, 100.0]
    hinge = _hinge(vals)
    mid = _midmean(vals)
    assert abs(hinge - mid) > 0.1
    rows = [
        {
            "antenna_id": f"H{i}",
            "x_m": 0.01 * i,
            "y_m": 0.0,
            "freq_hz": f,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        }
        for i, f in enumerate(vals)
    ]
    # hinge: lo=s[1]=2, hi=s[4]=30 → 16; midmean=mean(2,10,20,30)=15.5
    pol = dict(DESK)
    pol.update(
        {
            "freq_anchor": "hinge",
            "freq_match_eps_hz": max(abs(v - hinge) for v in vals) + 0.01,
            "ref_antenna_id": "H0",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
        }
    )
    assert max(abs(v - hinge) for v in vals) + 0.01 < max(abs(v - mid) for v in vals)
    _assert_pack(tmp_path, rows, pol)


def test_wrap_compose_modes_diverge_on_steer_phase(tmp_path: Path) -> None:
    """wrap_compose=wrap_each_then_sum must wrap residual and geo separately without a final wrap."""
    rows = [
        {
            "antenna_id": "W0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 3e8,
            "phase_meas_rad": 2.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "W1",
            "x_m": -2.0 / (2.0 * math.pi),
            "y_m": 0.0,
            "freq_hz": 3e8,
            "phase_meas_rad": 2.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "c_mps": 3e8,
            "steer_az_deg": 90.0,
            "steer_el_deg": 0.0,
            "el_law": "flat",
            "geo_sign": 1,
            "phase_sign": 1,
            "wrap_compose": "wrap_each_then_sum",
            "wrap_half_open": 1,
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "ref_antenna_id": "W0",
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    other = dict(pol)
    other["wrap_compose"] = "sum_then_wrap"
    alt = expect_desk(rows, other)
    w1 = next(e for e in exp["elems"] if e["antenna_id"] == "W1")
    a1 = next(e for e in alt["elems"] if e["antenna_id"] == "W1")
    # wrap_each → ~4.0; sum_then → ~4-2π
    assert abs(w1["steer_phase_rad"] - a1["steer_phase_rad"]) > 1.0


def test_steering_applies_geo_sign_and_cos_el(tmp_path: Path) -> None:
    """geo_sign and el_law=cos_el must both apply to the planar steering term."""
    rows = [
        {
            "antenna_id": "E0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 3e8,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "E1",
            "x_m": 0.25,
            "y_m": 0.0,
            "freq_hz": 3e8,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "c_mps": 3e8,
            "steer_az_deg": 90.0,
            "steer_el_deg": 60.0,
            "el_law": "cos_el",
            "geo_sign": -1,
            "phase_sign": 1,
            "wrap_compose": "sum_then_wrap",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "ref_antenna_id": "E0",
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    e1 = next(e for e in exp["elems"] if e["antenna_id"] == "E1")
    # raw_geo = -k * x * sin(90) * cos(60) = -2π*0.25*0.5 = -π/4
    # geo = -1 * raw = +π/4
    want = _wrap(math.pi / 4, 1)
    assert abs(math.atan2(e1["w_imag"], e1["w_real"]) - want) < 1e-9


def test_align_mode_div_ref_sets_ref_to_one(tmp_path: Path) -> None:
    """align_mode=div_ref must complex-divide by w_ref so the reference becomes 1+0i pre-norm."""
    rows = [
        {
            "antenna_id": "A0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.4,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "A1",
            "x_m": 0.05,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.1,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "ref_antenna_id": "A0",
            "ref_phase_align": 1,
            "align_mode": "div_ref",
            "norm_mode": "none",
            "outlier_mode": "union",
            "phase_sign": 1,
            "geo_sign": 1,
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    a0 = next(e for e in exp["elems"] if e["antenna_id"] == "A0")
    assert abs(a0["w_real"] - 1.0) < 1e-9
    assert abs(a0["w_imag"]) < 1e-9


def test_rms_over_full_array_when_basis_all(tmp_path: Path) -> None:
    """rms_basis=all must average delta^2 over every element including outliers."""
    rows = [
        {
            "antenna_id": "R0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "R1",
            "x_m": 0.05,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 1.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "phase_tol_rad": 0.1,
            "gain_tol_db": 10.0,
            "rms_basis": "all",
            "outlier_mode": "union",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_antenna_id": "R0",
            "ref_phase_align": 0,
            "norm_mode": "none",
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    assert abs(exp["rms"] - math.sqrt(0.5)) < 1e-12


def test_phase_gain_equality_is_not_outlier(tmp_path: Path) -> None:
    """Exact equality to phase_tol_rad or gain_tol_db must not mark a primary outlier."""
    rows = [
        {
            "antenna_id": "Q0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.15,
            "gain_err_db": 1.5,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "Q1",
            "x_m": 0.05,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "phase_tol_rad": 0.15,
            "gain_tol_db": 1.5,
            "outlier_mode": "union",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_antenna_id": "Q1",
            "ref_phase_align": 0,
            "norm_mode": "none",
        }
    )
    exp = _assert_pack(tmp_path, rows, pol, expect_rc=0)
    assert exp["outlier_ids"] == []


def test_unknown_flag_exit_two_keeps_artifacts(tmp_path: Path) -> None:
    """Unknown CLI flag exits 2 and must not rewrite existing weights/report files."""
    weights = tmp_path / "keep.csv"
    report = tmp_path / "keep.json"
    marker_w = b"WEIGHT_MARKER"
    marker_r = b"REPORT_MARKER"
    weights.write_bytes(marker_w)
    report.write_bytes(marker_r)
    proc = subprocess.run(
        [
            str(TOOL),
            "--lattice",
            str(SAMPLE),
            "--desk",
            str(LIVE_DESK),
            "--weights",
            str(weights),
            "--report",
            str(report),
            "--nope",
            "x",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr != ""
    assert weights.read_bytes() == marker_w
    assert report.read_bytes() == marker_r


def test_policy_schema_mismatch_is_fatal(tmp_path: Path) -> None:
    """schema_version other than 8 is a fatal desk error (exit 2, no outputs)."""
    pol = dict(DESK)
    pol["schema_version"] = 7
    desk = tmp_path / "d.toml"
    lat = tmp_path / "l.csv"
    weights = tmp_path / "w.csv"
    report = tmp_path / "r.json"
    desk.write_text(_toml(pol), encoding="utf-8")
    _write_lattice(
        lat,
        [
            {
                "antenna_id": "A00",
                "x_m": 0.0,
                "y_m": 0.0,
                "freq_hz": 1e9,
                "phase_meas_rad": 0.0,
                "gain_err_db": 0.0,
                "ref_phase_rad": 0.0,
            }
        ],
    )
    proc = _run(lat, desk, weights, report)
    assert proc.returncode == 2
    assert not weights.exists()
    assert not report.exists()


def test_duplicate_antenna_id_is_fatal(tmp_path: Path) -> None:
    """Duplicate antenna_id values are fatal and must not emit artifacts."""
    rows = [
        {
            "antenna_id": "X",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "X",
            "x_m": 0.01,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    desk = tmp_path / "d.toml"
    lat = tmp_path / "l.csv"
    weights = tmp_path / "w.csv"
    report = tmp_path / "r.json"
    desk.write_text(_toml(DESK), encoding="utf-8")
    _write_lattice(lat, rows)
    proc = _run(lat, desk, weights, report)
    assert proc.returncode == 2
    assert not weights.exists()


def test_absent_ref_antenna_is_fatal(tmp_path: Path) -> None:
    """Missing ref_antenna_id in the lattice is fatal."""
    rows = [
        {
            "antenna_id": "Z1",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        }
    ]
    pol = dict(DESK)
    pol["ref_antenna_id"] = "MISSING"
    desk = tmp_path / "d.toml"
    lat = tmp_path / "l.csv"
    weights = tmp_path / "w.csv"
    report = tmp_path / "r.json"
    desk.write_text(_toml(pol), encoding="utf-8")
    _write_lattice(lat, rows)
    proc = _run(lat, desk, weights, report)
    assert proc.returncode == 2


def test_wrong_csv_header_names_are_fatal(tmp_path: Path) -> None:
    """Header with correct arity but wrong names must exit 2."""
    lat = tmp_path / "bad_hdr.csv"
    lat.write_text(
        "id,x_m,y_m,freq_hz,phase_meas_rad,gain_err_db,ref_phase_rad\n"
        "A00,0,0,1e9,0,0,0\n",
        encoding="utf-8",
    )
    desk = tmp_path / "d.toml"
    weights = tmp_path / "w.csv"
    report = tmp_path / "r.json"
    desk.write_text(_toml(DESK), encoding="utf-8")
    proc = _run(lat, desk, weights, report)
    assert proc.returncode == 2


def test_lattice_accepts_crlf_comments_blanks(tmp_path: Path) -> None:
    """CRLF endings, # comments, and blank lines must parse like Unix LF packs."""
    body = (
        "antenna_id,x_m,y_m,freq_hz,phase_meas_rad,gain_err_db,ref_phase_rad\r\n"
        "# note\r\n"
        "\r\n"
        "A00,0,0,1000000000,0,0,0\r\n"
        "A01,0.05,0,1000000000,0.01,0.1,0\r\n"
    )
    lat = tmp_path / "crlf.csv"
    lat.write_bytes(body.encode("utf-8"))
    rows = _read_lattice(lat)
    pol = dict(DESK)
    pol.update(
        {
            "ref_antenna_id": "A00",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "ref_phase_align": 0,
        }
    )
    desk = tmp_path / "d.toml"
    weights = tmp_path / "w.csv"
    report = tmp_path / "r.json"
    desk.write_text(_toml(pol), encoding="utf-8")
    exp = expect_desk(rows, pol)
    proc = _run(lat, desk, weights, report)
    assert proc.returncode == exp["exit"]
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["cal_digest"] == exp["cal_digest"]


def test_cli_flag_order_does_not_change_digest(tmp_path: Path) -> None:
    """CLI flag order must not change exit code or digest for the same paths."""
    rows = _read_lattice(SAMPLE)
    exp = expect_desk(rows, DESK)
    w_a = tmp_path / "a.csv"
    r_a = tmp_path / "a.json"
    w_b = tmp_path / "b.csv"
    r_b = tmp_path / "b.json"
    p1 = subprocess.run(
        [
            str(TOOL),
            "--weights",
            str(w_a),
            "--lattice",
            str(SAMPLE),
            "--report",
            str(r_a),
            "--desk",
            str(LIVE_DESK),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    p2 = subprocess.run(
        [
            str(TOOL),
            "--report",
            str(r_b),
            "--desk",
            str(LIVE_DESK),
            "--weights",
            str(w_b),
            "--lattice",
            str(SAMPLE),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p1.returncode == p2.returncode == exp["exit"]
    assert json.loads(r_a.read_text())["cal_digest"] == json.loads(r_b.read_text())["cal_digest"]


def test_policy_revision_is_bound_into_digest(tmp_path: Path) -> None:
    """Changing policy_revision alone must change cal_digest while physics stay equal."""
    rows = [
        {
            "antenna_id": "K0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "K1",
            "x_m": 0.04,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.05,
            "gain_err_db": 0.2,
            "ref_phase_rad": 0.0,
        },
    ]
    pol_a = dict(DESK)
    pol_a.update(
        {
            "policy_revision": "rev-alpha",
            "ref_antenna_id": "K0",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
            "outlier_mode": "union",
            "mutual_alpha": 0.0,
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_phase_align": 0,
            "norm_mode": "none",
        }
    )
    pol_b = dict(pol_a)
    pol_b["policy_revision"] = "rev-beta"
    d1 = _assert_pack(tmp_path / "a", rows, pol_a)["cal_digest"]
    d2 = _assert_pack(tmp_path / "b", rows, pol_b)["cal_digest"]
    assert d1 != d2


def test_neighbor_radius_is_inclusive(tmp_path: Path) -> None:
    """Neighbors at exactly neighbor_radius_m must be included in mutual coupling."""
    rows = [
        {
            "antenna_id": "B0",
            "x_m": 0.0,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
        {
            "antenna_id": "B1",
            "x_m": 0.02,
            "y_m": 0.0,
            "freq_hz": 1e9,
            "phase_meas_rad": 0.0,
            "gain_err_db": 0.0,
            "ref_phase_rad": 0.0,
        },
    ]
    pol = dict(DESK)
    pol.update(
        {
            "neighbor_radius_m": 0.02,
            "mutual_alpha": 1.0,
            "mutual_kernel": "linear",
            "couple_mask": "all",
            "taper_beta": 0.0,
            "steer_az_deg": 0.0,
            "steer_el_deg": 0.0,
            "ref_antenna_id": "B0",
            "ref_phase_align": 0,
            "outlier_mode": "union",
            "norm_mode": "none",
            "phase_tol_rad": 10.0,
            "gain_tol_db": 10.0,
        }
    )
    exp = _assert_pack(tmp_path, rows, pol)
    b0 = next(e for e in exp["elems"] if e["antenna_id"] == "B0")
    assert abs(b0["couple"] - math.exp(-1.0)) < 1e-12


def test_identical_reruns_are_byte_stable(tmp_path: Path) -> None:
    """Two successful runs on identical inputs must produce byte-identical artifacts."""
    w1 = tmp_path / "1.csv"
    r1 = tmp_path / "1.json"
    w2 = tmp_path / "2.csv"
    r2 = tmp_path / "2.json"
    p1 = _run(SAMPLE, LIVE_DESK, w1, r1)
    p2 = _run(SAMPLE, LIVE_DESK, w2, r2)
    assert p1.returncode == p2.returncode
    assert w1.read_bytes() == w2.read_bytes()
    assert r1.read_bytes() == r2.read_bytes()
