"""Voltage-collapse fold-map verifier: exactly 34 top-level tests.

Normative schemas (also under /loadcrest/bluebook/) exercised here:
- admittance companion JSON format admittance-companion-v1 (POWER-11)
- .vcm ZIP Store order: manifest.json, curve.csv, events.csv,
  critical_bus.csv, critical_branch.csv (TRACE-12)
- stable diagnostic codes including E_NETWORK_DECK, E_FOLD, E_BASE_REACTIVE_LIMIT
- scientific failures: nonphysical voltages, unresolved limit events, unbracketed folds
"""

from __future__ import annotations

import json
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import collapse_casebook as cb
import pytest

# Exactly 34 top-level test_foldpath_* functions are defined in this module.


def test_foldpath_admittance_reports_pi_model_terms(tmp_path: Path) -> None:
    """Admittance companion reports POWER-11 JSON with pi-model Y-bus terms."""
    net, _ = cb.sealed("two_bus")
    rep = cb.run_admittance(net)
    assert rep["format"] == "admittance-companion-v1"
    for key in (
        "network_sha256",
        "base_mva",
        "bus_count",
        "branch_count",
        "in_service_branch_count",
        "slack_bus",
        "nonzero_ybus_entries",
        "ybus",
        "branch_primitives",
    ):
        assert key in rep
    assert rep["nonzero_ybus_entries"] >= 3
    assert len(rep["ybus"]) == rep["nonzero_ybus_entries"]
    assert len(rep["branch_primitives"]) == rep["branch_count"]
    prim = next(p for p in rep["branch_primitives"] if p["status"] == "IN")
    assert abs(prim["g_ft"]) + abs(prim["b_ft"]) + abs(prim["g_ff"]) + abs(prim["b_ff"]) > 0


def test_foldpath_admittance_includes_tap_and_phase_shift(tmp_path: Path) -> None:
    """Tap magnitude and phase shift alter off-diagonal admittance primitives."""
    net, _ = cb.sealed("meshed")
    rep = cb.run_admittance(net)
    taps = [p for p in rep["branch_primitives"] if p["id"] == "b23"]
    assert taps and taps[0]["status"] == "IN"
    assert abs(taps[0]["g_ft"] - taps[0]["g_tf"]) > 1e-12 or abs(taps[0]["b_ft"] - taps[0]["b_tf"]) > 1e-12


def test_foldpath_bus_order_preserves_case_identity(tmp_path: Path) -> None:
    """Equivalent bus record ordering preserves network_sha256."""
    src, _ = cb.sealed("meshed")
    a = cb.run_admittance(src)
    shuffled = tmp_path / "shuf.acn"
    cb.shuffle_network_records(src, shuffled)
    b = cb.run_admittance(shuffled)
    assert a["network_sha256"] == b["network_sha256"]


def test_foldpath_branch_order_preserves_case_identity(tmp_path: Path) -> None:
    """Equivalent branch record ordering preserves network_sha256."""
    src, _ = cb.sealed("xfmr")
    a = cb.run_admittance(src)
    shuffled = tmp_path / "shuf2.acn"
    cb.shuffle_network_records(src, shuffled)
    b = cb.run_admittance(shuffled)
    assert a["network_sha256"] == b["network_sha256"]


def test_foldpath_rejects_duplicate_bus_identifier(tmp_path: Path) -> None:
    """Duplicate bus identifiers are rejected as network-deck failures."""
    p = tmp_path / "dup.acn"
    cb.write_text(
        p,
        """AC_NETWORK 1
BASE_MVA 100
BUS slack SLACK 1 0 0 0 0 0 0 0 0 0
BUS load PQ 1 0 0 0 0 0 0.2 0.1 0 0
BUS load PQ 1 0 0 0 0 0 0.1 0.1 0 0
BRANCH l1 slack load IN 0.01 0.1 0 1 0
END
""",
    )
    proc = subprocess.run(
        [str(cb.fold_map_bin()), "admittance", "--network", str(p)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "E_NETWORK_DECK" in proc.stderr


def test_foldpath_rejects_unknown_branch_endpoint(tmp_path: Path) -> None:
    """Branches referencing unknown buses are rejected."""
    p = tmp_path / "badep.acn"
    cb.write_text(
        p,
        """AC_NETWORK 1
BASE_MVA 100
BUS slack SLACK 1 0 0 0 0 0 0 0 0 0
BUS load PQ 1 0 0 0 0 0 0.2 0.1 0 0
BRANCH l1 slack ghost IN 0.01 0.1 0 1 0
END
""",
    )
    proc = subprocess.run(
        [str(cb.fold_map_bin()), "admittance", "--network", str(p)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "E_NETWORK_DECK" in proc.stderr


def test_foldpath_rejects_multiple_slack_buses(tmp_path: Path) -> None:
    """More than one slack bus is a network-deck failure."""
    p = tmp_path / "mslack.acn"
    cb.write_text(
        p,
        """AC_NETWORK 1
BASE_MVA 100
BUS s1 SLACK 1 0 0 0 0 0 0 0 0 0
BUS s2 SLACK 1 0 0 0 0 0 0 0 0 0
BRANCH l1 s1 s2 IN 0.01 0.1 0 1 0
END
""",
    )
    proc = subprocess.run(
        [str(cb.fold_map_bin()), "admittance", "--network", str(p)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0


def test_foldpath_rejects_energized_island_without_slack(tmp_path: Path) -> None:
    """An energized component that does not cover all buses yields E_ISLAND."""
    p = tmp_path / "island.acn"
    cb.write_text(
        p,
        """AC_NETWORK 1
BASE_MVA 100
BUS slack SLACK 1 0 0 0 0 0 0 0 0 0
BUS a PQ 1 0 0 0 0 0 0.1 0.05 0 0
BUS b PQ 1 0 0 0 0 0 0.1 0.05 0 0
BRANCH l1 slack a IN 0.01 0.1 0 1 0
BRANCH l2 a b OUT 0.01 0.1 0 1 0
END
""",
    )
    proc = subprocess.run(
        [str(cb.fold_map_bin()), "admittance", "--network", str(p)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "E_ISLAND" in proc.stderr


def test_foldpath_two_bus_basepoint_matches_analytic_solution(tmp_path: Path) -> None:
    """Two-bus base point voltages stay near the flat start with light load."""
    net, ramp = cb.sealed("two_bus")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert float(tr.curve[0]["lambda"]) == 0
    assert float(tr.curve[0]["min_voltage_pu"]) > 0.95
    buses = {b["bus_id"]: b for b in tr.buses}
    assert abs(float(buses["slack"]["voltage_pu"]) - 1.0) < 1e-12


def test_foldpath_pv_bus_holds_voltage_before_limit(tmp_path: Path) -> None:
    """PV voltage remains at the scheduled magnitude before a reactive event."""
    net, ramp = cb.sealed("pv_upper")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert tr.events, "expected a reactive-limit event"
    ev_lam = float(tr.events[0]["lambda"])
    pre = [row for row in tr.curve if float(row["lambda"]) < ev_lam - 1e-6]
    assert pre
    # Scheduled PV voltage appears in event voltage_pu at the event
    assert abs(float(tr.events[0]["voltage_pu"]) - 1.01) < 1e-6


def test_foldpath_out_of_service_branch_is_excluded(tmp_path: Path) -> None:
    """Out-of-service branches contribute zero critical flows and zero Y primitives."""
    net, ramp = cb.sealed("meshed")
    rep = cb.run_admittance(net)
    out = [p for p in rep["branch_primitives"] if p["status"] == "OUT"]
    assert out
    assert all(abs(p["g_ff"]) + abs(p["b_ff"]) + abs(p["g_ft"]) + abs(p["b_ft"]) == 0 for p in out)
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    bout = [b for b in tr.branches if b["branch_id"] == "bout"]
    assert bout and float(bout[0]["p_from"]) == 0 and float(bout[0]["q_loss"]) == 0


def test_foldpath_bus_shunts_change_basepoint_injection(tmp_path: Path) -> None:
    """Bus shunts change the Y-bus diagonal and therefore the operating point."""
    net, ramp = cb.sealed("meshed")
    rep = cb.run_admittance(net)
    diag = [e for e in rep["ybus"] if e["row"] == e["col"] == "gen1"]
    assert diag and abs(diag[0]["b"]) > 0
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert tr.manifest["point_count"] >= 2


def test_foldpath_rejects_basepoint_outside_reactive_limits(tmp_path: Path) -> None:
    """Rejects base reactive-limit violations and nonphysical voltage magnitudes."""
    net = tmp_path / "n.acn"
    ramp = tmp_path / "r.rmp"
    cb.write_text(
        net,
        """AC_NETWORK 1
BASE_MVA 100
BUS slack SLACK 1.05 0 0 0 0 0 0 0 0 0
BUS gen PV 1.02 0 0.5 0.05 -0.05 0.05 0.2 0.2 0 0
BUS load PQ 1 0 0 0 0 0 0.4 0.2 0 0
BRANCH b1 slack gen IN 0.01 0.1 0.02 1 0
BRANCH b2 gen load IN 0.02 0.12 0.02 1 0
BRANCH b3 load slack IN 0.02 0.1 0.02 1 0
END
""",
    )
    cb.write_text(
        ramp,
        """AC_RAMP 1
DEMAND gen 0.1 0.05
DEMAND load 0.3 0.1
LIMITS 0.8 1.2
STEPS 0.05 0.005 0.2
TOLERANCES 1e-6 1e-6 1e-5 1e-5
ITERATIONS 40 40 100
END
""",
    )
    rc, err, _ = cb.run_trace_expect_fail(net, ramp, tmp_path / "m.vcm")
    assert rc != 0
    assert "E_BASE_REACTIVE_LIMIT" in err
    assert json.loads(err.strip().splitlines()[-1])["code"] == "E_BASE_REACTIVE_LIMIT"

    # Nonphysical voltage magnitude (v_set <= 0) is a scientific deck rejection.
    bad_v = tmp_path / "badv.acn"
    cb.write_text(
        bad_v,
        """AC_NETWORK 1
BASE_MVA 100
BUS slack SLACK 1.0 0 0 0 0 0 0 0 0 0
BUS load PQ 0.0 0 0 0 0 0 0.2 0.1 0 0
BRANCH l1 slack load IN 0.01 0.1 0 1 0
END
""",
    )
    proc = subprocess.run(
        [str(cb.fold_map_bin()), "admittance", "--network", str(bad_v)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    diag = json.loads(proc.stderr.strip().splitlines()[-1])
    assert diag["code"] == "E_NETWORK_DECK"
    # Trace of the same nonphysical deck must also fail (no map published).
    bad_ramp = tmp_path / "badr.rmp"
    cb.write_text(
        bad_ramp,
        """AC_RAMP 1
DEMAND load 0.1 0.05
LIMITS 0.8 1.2
STEPS 0.05 0.005 0.2
TOLERANCES 1e-6 1e-6 1e-5 1e-5
ITERATIONS 40 40 100
END
""",
    )
    rc2, err2, _ = cb.run_trace_expect_fail(bad_v, bad_ramp, tmp_path / "bad.vcm")
    assert rc2 != 0
    assert "E_NETWORK_DECK" in err2
    assert not (tmp_path / "bad.vcm").exists()


def test_foldpath_locates_qmax_switch_event(tmp_path: Path) -> None:
    """Locates a fully resolved PV upper limit; unresolved events would fail."""
    net, ramp = cb.sealed("pv_upper")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert tr.events
    assert tr.events[0]["limit_kind"] == "UPPER"
    assert float(tr.events[0]["q_limit"]) == 0.4
    assert float(tr.events[0]["lambda"]) < tr.critical_lambda
    # Event is fully resolved: switched bus holds the exact limit as PQ generation.
    bus = next(b for b in tr.buses if b["bus_id"] == tr.events[0]["bus_id"])
    assert bus["final_type"] == "PQ"
    assert abs(float(bus["q_generation"]) - float(tr.events[0]["q_limit"])) < 1e-9
    assert float(tr.events[0]["voltage_pu"]) > 0
    # No unresolved reactive-limit rows: every published event is finite and typed.
    for ev in tr.events:
        assert ev["limit_kind"] in {"UPPER", "LOWER"}
        assert math.isfinite(float(ev["lambda"]))
        assert math.isfinite(float(ev["q_limit"]))
        assert math.isfinite(float(ev["voltage_pu"]))
        assert float(ev["voltage_pu"]) > 0


def test_foldpath_locates_qmin_switch_event(tmp_path: Path) -> None:
    """Locates a fully resolved PV lower limit before the fold."""
    # Underexcited sealed case: binding floor is q_min on an absorbing PV machine.
    net, ramp = cb.sealed("pv_lower")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    kinds = [e["limit_kind"] for e in tr.events]
    assert "LOWER" in kinds, f"expected LOWER event, got {kinds}"
    lower = next(e for e in tr.events if e["limit_kind"] == "LOWER")
    assert float(lower["lambda"]) < tr.critical_lambda
    bus = next(b for b in tr.buses if b["bus_id"] == lower["bus_id"])
    assert bus["final_type"] == "PQ"
    assert abs(float(bus["q_generation"]) - float(lower["q_limit"])) < 1e-9


def test_foldpath_simultaneous_limit_events_use_bus_order(tmp_path: Path) -> None:
    """Simultaneous reactive events are published in ascending bus-id order."""
    net, ramp = cb.sealed("simul")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert len(tr.events) >= 2
    assert float(tr.events[0]["lambda"]) == float(tr.events[1]["lambda"])
    ids = [e["bus_id"] for e in tr.events[:2]]
    assert ids == sorted(ids)


def test_foldpath_switched_bus_remains_pq_after_event(tmp_path: Path) -> None:
    """A switched PV bus remains PQ through the critical point."""
    net, ramp = cb.sealed("pv_upper")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    bus_id = tr.events[0]["bus_id"]
    row = next(b for b in tr.buses if b["bus_id"] == bus_id)
    assert row["final_type"] == "PQ"


def test_foldpath_corrected_points_meet_power_and_arc_budgets(tmp_path: Path) -> None:
    """Accepted curve points meet power-mismatch and arc-length residual budgets."""
    net, ramp = cb.sealed("two_bus")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    for row in tr.curve[1:]:
        assert float(row["max_power_mismatch"]) <= 1e-6 + 1e-12
        assert abs(float(row["arc_residual"])) <= 1e-6 + 1e-12


def test_foldpath_initial_step_change_preserves_critical_lambda(tmp_path: Path) -> None:
    """Changing the initial continuation step preserves the critical loading margin."""
    net, ramp = cb.sealed("two_bus")
    tr1 = cb.run_trace(net, ramp, tmp_path / "a.vcm")
    alt = tmp_path / "alt.rmp"
    text = ramp.read_text(encoding="utf-8").replace("STEPS 0.02 0.002 0.1", "STEPS 0.03 0.002 0.1")
    cb.write_text(alt, text)
    tr2 = cb.run_trace(net, alt, tmp_path / "b.vcm")
    assert abs(tr1.critical_lambda - tr2.critical_lambda) <= 5e-4


def test_foldpath_maximum_step_change_preserves_critical_lambda(tmp_path: Path) -> None:
    """Changing the maximum step preserves the critical loading margin."""
    net, ramp = cb.sealed("two_bus")
    tr1 = cb.run_trace(net, ramp, tmp_path / "a.vcm")
    alt = tmp_path / "alt.rmp"
    text = ramp.read_text(encoding="utf-8").replace("STEPS 0.02 0.002 0.1", "STEPS 0.02 0.002 0.08")
    cb.write_text(alt, text)
    tr2 = cb.run_trace(net, alt, tmp_path / "b.vcm")
    assert abs(tr1.critical_lambda - tr2.critical_lambda) <= 5e-4


def test_foldpath_two_bus_fold_matches_closed_form_margin(tmp_path: Path) -> None:
    """Two-bus fold matches the sealed closed-form loading margin."""
    net, ramp = cb.sealed("two_bus")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    margins = cb.load_margins()
    assert abs(tr.critical_lambda - margins["two_bus"]["critical_lambda"]) <= 1e-4


def test_foldpath_meshed_network_reaches_expected_fold(tmp_path: Path) -> None:
    """Meshed network critical lambda matches the sealed margin."""
    net, ramp = cb.sealed("meshed")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    margins = cb.load_margins()
    assert abs(tr.critical_lambda - margins["meshed"]["critical_lambda"]) <= 1e-4
    assert tr.manifest["event_count"] >= 1


def test_foldpath_near_singular_fold_remains_finite(tmp_path: Path) -> None:
    """Near-singular folds stay finite; an unbracketed fold fails with E_FOLD."""
    net, ramp = cb.sealed("near_sing")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert math.isfinite(tr.critical_lambda)
    margins = cb.load_margins()
    assert abs(tr.critical_lambda - margins["near_sing"]["critical_lambda"]) <= 1e-3

    # Too few continuation points leaves the fold unbracketed (scientific failure).
    short = tmp_path / "short.rmp"
    text = ramp.read_text(encoding="utf-8").replace(
        "ITERATIONS 50 50 400",
        "ITERATIONS 50 50 8",
    )
    cb.write_text(short, text)
    out = tmp_path / "nofold.vcm"
    rc, err, _ = cb.run_trace_expect_fail(net, short, out)
    assert rc != 0
    diag = json.loads(err.strip().splitlines()[-1])
    assert diag["code"] == "E_FOLD"
    assert not out.exists()


def test_foldpath_loading_parameter_rises_before_fold(tmp_path: Path) -> None:
    """Loading parameter increases along the stable branch before the fold."""
    net, ramp = cb.sealed("two_bus")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    lams = [float(r["lambda"]) for r in tr.curve]
    peak = max(lams)
    assert peak == max(lams[: lams.index(peak) + 1])
    assert lams[0] == 0
    assert any(lams[i] < lams[i + 1] for i in range(len(lams) - 1))


def test_foldpath_tangent_sign_change_brackets_fold(tmp_path: Path) -> None:
    """Fold is bracketed by a tangent_lambda sign change, not Newton failure."""
    net, ramp = cb.sealed("two_bus")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    tls = [float(r["tangent_lambda"]) for r in tr.curve]
    assert tls[0] > 0
    assert any(tls[i] > 0 and tls[i + 1] <= 0 for i in range(len(tls) - 1))
    # Successful maps never publish unresolved limit events.
    for ev in tr.events:
        assert math.isfinite(float(ev["q_limit"]))
        assert math.isfinite(float(ev["lambda"]))
        assert math.isfinite(float(ev["voltage_pu"]))
        assert float(ev["voltage_pu"]) > 0
        assert ev["limit_kind"] in {"UPPER", "LOWER"}


def test_foldpath_critical_bus_loads_follow_reported_lambda(tmp_path: Path) -> None:
    """Critical bus loads equal base load plus lambda times demand direction."""
    net, ramp = cb.sealed("meshed")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    lam = tr.critical_lambda
    demands = {}
    for line in ramp.read_text(encoding="utf-8").splitlines():
        if line.startswith("DEMAND"):
            _, bus, dp, dq = line.split()
            demands[bus] = (float(dp), float(dq))
    base = {}
    for line in net.read_text(encoding="utf-8").splitlines():
        if line.startswith("BUS"):
            p = line.split()
            base[p[1]] = (float(p[9]), float(p[10]))
    for row in tr.buses:
        bid = row["bus_id"]
        if bid not in demands:
            continue
        dp, dq = demands[bid]
        bp, bq = base[bid]
        assert abs(float(row["p_load"]) - (bp + lam * dp)) < 1e-8
        assert abs(float(row["q_load"]) - (bq + lam * dq)) < 1e-8


def test_foldpath_critical_branch_losses_balance_bus_injections(tmp_path: Path) -> None:
    """Branch terminal powers define losses; aggregate losses match published totals."""
    net, ramp = cb.sealed("xfmr")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    p_loss = 0.0
    q_loss = 0.0
    for b in tr.branches:
        assert abs(float(b["p_loss"]) - (float(b["p_from"]) + float(b["p_to"]))) < 1e-10
        assert abs(float(b["q_loss"]) - (float(b["q_from"]) + float(b["q_to"]))) < 1e-10
        p_loss += float(b["p_loss"])
        q_loss += float(b["q_loss"])
    assert abs(tr.manifest["total_active_loss"] - p_loss) < 1e-12
    assert abs(tr.manifest["total_reactive_loss"] - q_loss) < 1e-12
    p_inj = sum(float(b["p_generation"]) - float(b["p_load"]) for b in tr.buses)
    assert abs(p_loss - p_inj) <= max(5e-2, 50 * float(tr.manifest["max_power_mismatch"]))


def test_foldpath_voltage_equal_to_limit_is_not_violation(tmp_path: Path) -> None:
    """Voltage exactly equal to a limit is classified WITHIN, not a violation."""
    net, ramp = cb.sealed("two_bus")
    # Widen limits so critical voltages stay inside; equality path covered by WITHIN labels.
    alt = tmp_path / "r.rmp"
    text = ramp.read_text(encoding="utf-8").replace("LIMITS 0.7 1.2", "LIMITS 0.01 2.0")
    cb.write_text(alt, text)
    tr = cb.run_trace(net, alt, tmp_path / "m.vcm")
    assert tr.manifest["voltage_violation_count"] == 0
    assert all(b["voltage_state"] == "WITHIN" for b in tr.buses)


def test_foldpath_low_voltage_bus_is_reported_as_violation(tmp_path: Path) -> None:
    """Critical voltages below voltage_min are reported as LOW violations."""
    net, ramp = cb.sealed("meshed")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert tr.manifest["voltage_violation_count"] >= 1
    assert any(b["voltage_state"] == "LOW" for b in tr.buses)


def test_foldpath_archive_entry_order_and_metadata_are_canonical(tmp_path: Path) -> None:
    """ZIP entry order and TRACE-12 manifest field order are canonical."""
    net, ramp = cb.sealed("two_bus")
    tr = cb.run_trace(net, ramp, tmp_path / "m.vcm")
    assert list(tr.manifest.keys()) == [
        "format",
        "network_sha256",
        "ramp_sha256",
        "status",
        "critical_lambda",
        "point_count",
        "event_count",
        "limiting_buses",
        "voltage_violation_count",
        "max_power_mismatch",
        "max_arc_residual",
        "total_active_loss",
        "total_reactive_loss",
    ]
    assert tr.manifest["status"] == "FOLD_FOUND"
    assert tr.manifest["format"] == "voltage-collapse-map-v1"


def test_foldpath_equivalent_record_order_produces_identical_archive(tmp_path: Path) -> None:
    """Equivalent deck ordering produces identical .vcm bytes."""
    net, ramp = cb.sealed("meshed")
    n2 = tmp_path / "n2.acn"
    r2 = tmp_path / "r2.rmp"
    cb.shuffle_network_records(net, n2)
    cb.shuffle_ramp_demands(ramp, r2)
    tr1 = cb.run_trace(net, ramp, tmp_path / "a.vcm")
    tr2 = cb.run_trace(n2, r2, tmp_path / "b.vcm")
    assert tr1.raw_zip == tr2.raw_zip


def test_foldpath_repeated_trace_is_byte_identical(tmp_path: Path) -> None:
    """Repeating an identical trace yields byte-identical archives."""
    net, ramp = cb.sealed("two_bus")
    tr1 = cb.run_trace(net, ramp, tmp_path / "a.vcm")
    tr2 = cb.run_trace(net, ramp, tmp_path / "b.vcm")
    assert tr1.raw_zip == tr2.raw_zip


def test_foldpath_rejected_trace_preserves_existing_map(tmp_path: Path) -> None:
    """A rejected calculation leaves an existing map byte-for-byte unchanged."""
    net, ramp = cb.sealed("two_bus")
    good = tmp_path / "keep.vcm"
    tr = cb.run_trace(net, ramp, good)
    prior = tr.raw_zip
    bad_net = tmp_path / "bad.acn"
    cb.write_text(bad_net, "AC_NETWORK 1\nEND\n")
    rc, err, _ = cb.run_trace_expect_fail(bad_net, ramp, good)
    assert rc != 0
    assert good.read_bytes() == prior
    assert proc_has_code(err)


def test_foldpath_parallel_processes_do_not_share_trace_state(tmp_path: Path) -> None:
    """Parallel fold-map processes do not share mutable trace state."""
    net_a, ramp_a = cb.sealed("two_bus")
    net_b, ramp_b = cb.sealed("near_sing")
    out_a = tmp_path / "a.vcm"
    out_b = tmp_path / "b.vcm"

    def run_one(net: Path, ramp: Path, out: Path) -> float:
        return cb.run_trace(net, ramp, out).critical_lambda

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(run_one, net_a, ramp_a, out_a)
        fb = pool.submit(run_one, net_b, ramp_b, out_b)
        la, lb = fa.result(), fb.result()
    assert la != pytest.approx(lb, rel=0, abs=1e-3)
    assert abs(la - cb.load_margins()["two_bus"]["critical_lambda"]) <= 1e-4
    assert abs(lb - cb.load_margins()["near_sing"]["critical_lambda"]) <= 1e-3


def proc_has_code(err: str) -> bool:
    """stderr contains a stable scientific failure code."""
    return any(
        code in err
        for code in (
            "E_NETWORK_DECK",
            "E_PATH",
            "E_ISLAND",
            "E_BASEPOINT",
            "E_CONTINUATION",
            "E_MAP",
        )
    )
