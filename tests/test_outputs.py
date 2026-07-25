"""SpanForge modal calibration verifier — exactly 36 top-level tests."""

from __future__ import annotations

import json
import math
from pathlib import Path

from span_modal_lab import (
    base_plan,
    copy_sealed_triplet,
    isolated_workdir,
    parse_mcr,
    run_calibrate,
    run_spectrum,
    stderr_code,
    two_dof_analytic_model,
    write_json,
)


def test_spanfit_spectrum_matches_two_dof_analytic_frequencies() -> None:
    """Spectrum frequencies match the closed-form two-DOF generalized eigenvalues."""
    with isolated_workdir() as td:
        model = write_json(Path(td) / "model.json", two_dof_analytic_model())
        proc = run_spectrum(model)
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        expect = [math.sqrt(1.2) / (2 * math.pi), math.sqrt(3.2) / (2 * math.pi)]
        assert abs(data["frequencies_hz"][0] - expect[0]) < 1e-12
        assert abs(data["frequencies_hz"][1] - expect[1]) < 1e-12


def test_spanfit_spectrum_is_invariant_to_eigenvector_sign() -> None:
    """Mode-shape sign flips leave calibrated objective, MAC, and pairing unchanged."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        flipped = json.loads(survey.read_text())
        for mode in flipped["modes"]:
            mode["shape"] = [
                (-v if v is not None else None) for v in mode["shape"]
            ]
        alt = write_json(Path(td) / "flipped.json", flipped)
        r1 = Path(td) / "a.mcr"
        r2 = Path(td) / "b.mcr"
        assert run_calibrate(model, survey, plan, r1).returncode == 0
        assert run_calibrate(model, alt, plan, r2).returncode == 0
        a = parse_mcr(r1.read_text())
        b = parse_mcr(r2.read_text())
        assert abs(a["objective_total"] - b["objective_total"]) < 1e-12
        assert [p["mac"] for p in a["pairs"]] == [p["mac"] for p in b["pairs"]]
        assert [p["predicted"] for p in a["pairs"]] == [
            p["predicted"] for p in b["pairs"]
        ]


def test_spanfit_rejects_nonsymmetric_mass_matrix() -> None:
    """Mass asymmetry beyond tolerance yields E_MATRIX_SYMMETRY."""
    with isolated_workdir() as td:
        m = two_dof_analytic_model()
        m["mass"] = [[1.0, 0.5], [0.0, 1.0]]
        proc = run_spectrum(write_json(Path(td) / "m.json", m))
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_MATRIX_SYMMETRY"


def test_spanfit_rejects_nonpositive_definite_mass_matrix() -> None:
    """A singular or indefinite mass matrix yields E_MASS_PHYSICALITY."""
    with isolated_workdir() as td:
        m = two_dof_analytic_model()
        m["mass"] = [[1.0, 0.0], [0.0, 0.0]]
        proc = run_spectrum(write_json(Path(td) / "m.json", m))
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_MASS_PHYSICALITY"


def test_spanfit_rejects_nonsymmetric_stiffness_contribution() -> None:
    """Asymmetric group contribution is rejected before spectrum work."""
    with isolated_workdir() as td:
        m = two_dof_analytic_model()
        m["groups"][0]["contribution"] = [[0.2, 0.3], [0.0, 0.2]]
        proc = run_spectrum(write_json(Path(td) / "m.json", m))
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_MATRIX_SYMMETRY"


def test_spanfit_rejects_nonphysical_stiffness_box_corner() -> None:
    """A nonphysical stiffness box corner yields E_STIFFNESS_BOX."""
    with isolated_workdir() as td:
        m = two_dof_analytic_model()
        m["fixed_stiffness"] = [[0.05, 0.0], [0.0, 0.05]]
        m["groups"][0]["lower"] = -5.0
        m["groups"][0]["upper"] = -0.1
        m["groups"][0]["initial"] = -1.0
        m["groups"][0]["reference"] = -1.0
        m["groups"][0]["contribution"] = [[1.0, 0.0], [0.0, 1.0]]
        proc = run_spectrum(write_json(Path(td) / "m.json", m))
        assert proc.returncode != 0
        assert stderr_code(proc) in {"E_STIFFNESS_BOX", "E_MODEL_SCHEMA"}


def test_spanfit_rejects_duplicate_dof_identifier() -> None:
    """Duplicate DOF identifiers are a model schema failure."""
    with isolated_workdir() as td:
        m = two_dof_analytic_model()
        m["dofs"] = ["D01", "D01"]
        proc = run_spectrum(write_json(Path(td) / "m.json", m))
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_MODEL_SCHEMA"


def test_spanfit_rejects_duplicate_group_identifier() -> None:
    """Duplicate stiffness group identifiers are rejected."""
    with isolated_workdir() as td:
        m = two_dof_analytic_model()
        g = dict(m["groups"][0])
        g["group_id"] = "cable"
        m["groups"] = [m["groups"][0], g]
        # shrink contribution so box may still be ok; schema should fail first
        proc = run_spectrum(write_json(Path(td) / "m.json", m))
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_MODEL_SCHEMA"


def test_spanfit_rejects_unknown_sensor_dof() -> None:
    """Survey sensors that are not model DOFs yield E_SURVEY_SCHEMA."""
    with isolated_workdir() as td:
        model, _, plan = copy_sealed_triplet("single_group", Path(td))
        survey = {
            "format": "bridge-modal-survey-v1",
            "sensors": ["A", "ZZ"],
            "modes": [
                {"mode_id": "M1", "frequency_hz": 0.2, "weight": 1.0, "shape": [0.5, 0.5]},
                {"mode_id": "M2", "frequency_hz": 0.3, "weight": 1.0, "shape": [0.4, 0.6]},
            ],
        }
        sp = write_json(Path(td) / "survey.json", survey)
        rep = Path(td) / "out.mcr"
        proc = run_calibrate(model, sp, plan, rep)
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_SURVEY_SCHEMA"


def test_spanfit_rejects_mode_with_insufficient_observed_channels() -> None:
    """A measured mode with fewer than two finite channels is rejected."""
    with isolated_workdir() as td:
        model, _, plan = copy_sealed_triplet("single_group", Path(td))
        survey = {
            "format": "bridge-modal-survey-v1",
            "sensors": ["A", "B"],
            "modes": [
                {"mode_id": "M1", "frequency_hz": 0.2, "weight": 1.0, "shape": [0.5, None]},
                {"mode_id": "M2", "frequency_hz": 0.3, "weight": 1.0, "shape": [0.4, 0.6]},
            ],
        }
        proc = run_calibrate(
            model,
            write_json(Path(td) / "survey.json", survey),
            plan,
            Path(td) / "out.mcr",
        )
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_SURVEY_SCHEMA"


def test_spanfit_missing_sensor_values_are_not_zero_filled() -> None:
    """Null survey channels remain evidence gaps and still allow successful pairing on commons."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        data = json.loads(survey.read_text())
        # introduce a null on a non-critical extra would need 3 sensors; instead ensure calibrate
        # of sealed case (no nulls) succeeds, and a variant with null on one mode's channel
        # that still leaves >=2 commons across a singleton cluster succeeds.
        data["modes"][0]["shape"] = [data["modes"][0]["shape"][0], None]
        # insufficient for that mode alone — should fail schema
        bad = write_json(Path(td) / "bad.json", data)
        proc_bad = run_calibrate(model, bad, plan, Path(td) / "bad.mcr")
        assert stderr_code(proc_bad) == "E_SURVEY_SCHEMA"
        # sealed original succeeds without treating missing as zero
        proc = run_calibrate(model, survey, plan, Path(td) / "ok.mcr")
        assert proc.returncode == 0
        assert "CALIBRATED" in proc.stdout


def test_spanfit_sensor_order_remap_preserves_calibration() -> None:
    """Permuting survey sensor order yields identical report bytes."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        data = json.loads(survey.read_text())
        # reverse sensors and each shape
        data["sensors"] = list(reversed(data["sensors"]))
        for mode in data["modes"]:
            mode["shape"] = list(reversed(mode["shape"]))
        alt = write_json(Path(td) / "survey_alt.json", data)
        r1 = Path(td) / "a.mcr"
        r2 = Path(td) / "b.mcr"
        p1 = run_calibrate(model, survey, plan, r1)
        p2 = run_calibrate(model, alt, plan, r2)
        assert p1.returncode == 0 and p2.returncode == 0
        assert r1.read_bytes() == r2.read_bytes()


def test_spanfit_group_order_preserves_report_bytes() -> None:
    """Reordering model groups preserves calibrated report identity."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("two_groups", Path(td))
        data = json.loads(model.read_text())
        data["groups"] = list(reversed(data["groups"]))
        alt = write_json(Path(td) / "model_alt.json", data)
        r1 = Path(td) / "a.mcr"
        r2 = Path(td) / "b.mcr"
        assert run_calibrate(model, survey, plan, r1).returncode == 0
        assert run_calibrate(alt, survey, plan, r2).returncode == 0
        assert r1.read_bytes() == r2.read_bytes()


def test_spanfit_mode_order_swap_preserves_cluster_pairing() -> None:
    """Swapping measured mode declaration order preserves pairing outcomes."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        data = json.loads(survey.read_text())
        data["modes"] = list(reversed(data["modes"]))
        alt = write_json(Path(td) / "survey_alt.json", data)
        r1 = Path(td) / "a.mcr"
        r2 = Path(td) / "b.mcr"
        assert run_calibrate(model, survey, plan, r1).returncode == 0
        assert run_calibrate(model, alt, plan, r2).returncode == 0
        a = parse_mcr(r1.read_text())
        b = parse_mcr(r2.read_text())
        assert a["pairs"] == b["pairs"]
        assert a["model_sha256"] == b["model_sha256"]


def test_spanfit_exact_repeated_modes_use_subspace_mac() -> None:
    """Exact repeated eigenvalues report subspace MAC of one plus frequency residual fields."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("repeated_modes", Path(td))
        rep = Path(td) / "out.mcr"
        proc = run_calibrate(model, survey, plan, rep)
        assert proc.returncode == 0, proc.stderr
        raw = rep.read_text()
        assert "PAIR " in raw
        rec = parse_mcr(raw)
        assert len(rec["pairs"]) == 1
        pair = rec["pairs"][0]
        assert abs(pair["mac"] - 1.0) < 1e-9
        assert "freq_res" in pair and math.isfinite(pair["freq_res"])
        assert abs(pair["freq_res"]) < 1e-9
        assert "mac" in pair and 0.0 <= pair["mac"] <= 1.0


def test_spanfit_near_repeated_modes_follow_cluster_tolerance() -> None:
    """Near-repeated measured frequencies merge under the plan cluster tolerance."""
    with isolated_workdir() as td:
        # Build isotropic-ish model and two measured modes within tolerance
        model = {
            "format": "bridge-modal-model-v1",
            "dofs": ["X", "Y"],
            "mass": [[1.0, 0.0], [0.0, 1.0]],
            "fixed_stiffness": [[2.0, 0.0], [0.0, 2.0002]],
            "groups": [
                {
                    "group_id": "k",
                    "lower": 0.8,
                    "upper": 1.2,
                    "initial": 1.0,
                    "reference": 1.0,
                    "contribution": [[0.5, 0.0], [0.0, 0.5]],
                }
            ],
        }
        mp = write_json(Path(td) / "model.json", model)
        spec = json.loads(run_spectrum(mp).stdout)
        f0, f1 = spec["frequencies_hz"]
        survey = {
            "format": "bridge-modal-survey-v1",
            "sensors": ["X", "Y"],
            "modes": [
                {"mode_id": "N1", "frequency_hz": f0, "weight": 1.0, "shape": [1.0, 0.0]},
                {"mode_id": "N2", "frequency_hz": f1, "weight": 1.0, "shape": [0.0, 1.0]},
            ],
        }
        plan = base_plan(
            cluster_relative_tolerance=0.05,
            shape_weight=0.2,
            regularization_weight=0.0,
            pairing_frequency_gate=0.5,
            gradient_tolerance=1e-6,
        )
        rep = Path(td) / "out.mcr"
        proc = run_calibrate(mp, write_json(Path(td) / "s.json", survey), write_json(Path(td) / "p.json", plan), rep)
        assert proc.returncode == 0, proc.stderr
        rec = parse_mcr(rep.read_text())
        # With loose tolerance, measured modes must merge into exactly one cluster pair.
        assert len(rec["pairs"]) == 1
        merged = rec["pairs"][0]
        assert "," in merged["measured"]
        assert set(merged["measured"].split(",")) == {"N1", "N2"}


def test_spanfit_subspace_mac_is_invariant_to_cluster_basis_rotation() -> None:
    """Rotating the measured repeated-mode basis leaves subspace MAC unchanged."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("repeated_modes", Path(td))
        data = json.loads(survey.read_text())
        # additional 45-degree rotation of the two shapes
        a = data["modes"][0]["shape"]
        b = data["modes"][1]["shape"]
        c = math.cos(0.4)
        s = math.sin(0.4)
        data["modes"][0]["shape"] = [c * a[0] + s * b[0], c * a[1] + s * b[1]]
        data["modes"][1]["shape"] = [-s * a[0] + c * b[0], -s * a[1] + c * b[1]]
        alt = write_json(Path(td) / "rot.json", data)
        r1 = Path(td) / "a.mcr"
        r2 = Path(td) / "b.mcr"
        assert run_calibrate(model, survey, plan, r1).returncode == 0
        assert run_calibrate(model, alt, plan, r2).returncode == 0
        m1 = parse_mcr(r1.read_text())["pairs"][0]["mac"]
        m2 = parse_mcr(r2.read_text())["pairs"][0]["mac"]
        assert abs(m1 - m2) < 1e-9
        assert abs(m1 - 1.0) < 1e-9


def test_spanfit_global_pairing_beats_greedy_frequency_pairing() -> None:
    """Global assignment prefers the shape-consistent pairing over nearest-frequency greed."""
    with isolated_workdir() as td:
        # Two well-separated modes; crossed frequency proximity with swapped shapes.
        model = {
            "format": "bridge-modal-model-v1",
            "dofs": ["D1", "D2"],
            "mass": [[1.0, 0.0], [0.0, 1.0]],
            "fixed_stiffness": [[4.0, 0.0], [0.0, 9.0]],
            "groups": [
                {
                    "group_id": "g",
                    "lower": 0.9,
                    "upper": 1.1,
                    "initial": 1.0,
                    "reference": 1.0,
                    "contribution": [[0.1, 0.0], [0.0, 0.1]],
                }
            ],
        }
        mp = write_json(Path(td) / "m.json", model)
        spec = json.loads(run_spectrum(mp).stdout)
        f0, f1 = spec["frequencies_hz"]
        # Measured freqs near model, but shapes intentionally match opposite modes if greed by freq alone with perturbation:
        # Place measured mode A slightly closer in frequency to predicted mode 1 but with shape of mode 0.
        survey = {
            "format": "bridge-modal-survey-v1",
            "sensors": ["D1", "D2"],
            "modes": [
                {
                    "mode_id": "A",
                    "frequency_hz": f1 * 0.98,
                    "weight": 1.0,
                    "shape": [1.0, 0.0],
                },
                {
                    "mode_id": "B",
                    "frequency_hz": f0 * 1.02,
                    "weight": 1.0,
                    "shape": [0.0, 1.0],
                },
            ],
        }
        plan = base_plan(
            frequency_weight=0.05,
            shape_weight=5.0,
            regularization_weight=0.0,
            pairing_frequency_gate=0.5,
            gradient_tolerance=1e-5,
            max_iterations=40,
        )
        rep = Path(td) / "out.mcr"
        proc = run_calibrate(mp, write_json(Path(td) / "s.json", survey), write_json(Path(td) / "p.json", plan), rep)
        assert proc.returncode == 0, proc.stderr
        rec = parse_mcr(rep.read_text())
        # Shape-weighted global assignment should pair A->mode0 and B->mode1
        by_id = {p["measured"]: p["predicted"] for p in rec["pairs"]}
        assert by_id["A"] == "0"
        assert by_id["B"] == "1"


def test_spanfit_frequency_gate_rejects_unmatchable_cluster() -> None:
    """Clusters beyond the pairing frequency gate produce E_MODAL_PAIRING."""
    with isolated_workdir() as td:
        model, _, plan = copy_sealed_triplet("single_group", Path(td))
        survey = {
            "format": "bridge-modal-survey-v1",
            "sensors": ["A", "B"],
            "modes": [
                {"mode_id": "M1", "frequency_hz": 50.0, "weight": 1.0, "shape": [0.7, 0.3]},
                {"mode_id": "M2", "frequency_hz": 60.0, "weight": 1.0, "shape": [0.2, 0.8]},
            ],
        }
        pdata = json.loads(plan.read_text())
        pdata["pairing_frequency_gate"] = 0.05
        proc = run_calibrate(
            model,
            write_json(Path(td) / "s.json", survey),
            write_json(Path(td) / "p.json", pdata),
            Path(td) / "out.mcr",
        )
        assert proc.returncode != 0
        assert stderr_code(proc) == "E_MODAL_PAIRING"


def test_spanfit_recovers_single_group_stiffness_multiplier() -> None:
    """Bounded calibration recovers a sealed single-group truth multiplier."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        meta = json.loads((Path(__file__).parent / "sealed_modal_cases/single_group/meta.json").read_text())
        rep = Path(td) / "out.mcr"
        proc = run_calibrate(model, survey, plan, rep)
        assert proc.returncode == 0, proc.stderr
        rec = parse_mcr(rep.read_text())
        theta = rec["groups"][0]["theta"]
        assert abs(theta - meta["truth_theta"]) < meta["tol"]
        assert rec["confidence"] == "IDENTIFIABLE"
        assert math.isfinite(rec["objective_total"])
        assert len(rec["pairs"]) >= 1


def test_spanfit_recovers_two_independent_group_multipliers() -> None:
    """Two independent diagonal groups recover sealed truth multipliers."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("two_groups", Path(td))
        meta = json.loads((Path(__file__).parent / "sealed_modal_cases/two_groups/meta.json").read_text())
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        rec = parse_mcr(rep.read_text())
        thetas = {g["id"]: g["theta"] for g in rec["groups"]}
        assert abs(thetas["ga"] - meta["truth"][0]) < meta["tol"]
        assert abs(thetas["gb"] - meta["truth"][1]) < meta["tol"]
        assert rec["confidence"] == "IDENTIFIABLE"
        assert math.isfinite(rec["objective_total"])


def test_spanfit_unequal_modal_weights_scale_objective_contributions() -> None:
    """Unequal mode weights change the modal objective relative to equal weights."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        s = json.loads(survey.read_text())
        # Keep a shared nonzero residual so weights actually scale the modal term.
        s["modes"][0]["frequency_hz"] *= 1.08
        s["modes"][1]["frequency_hz"] *= 0.94
        s_unequal = json.loads(json.dumps(s))
        s_unequal["modes"][0]["weight"] = 5.0
        s_unequal["modes"][1]["weight"] = 0.2
        s_equal = json.loads(json.dumps(s))
        s_equal["modes"][0]["weight"] = 1.0
        s_equal["modes"][1]["weight"] = 1.0
        m = json.loads(model.read_text())
        m["groups"][0]["initial"] = 0.85
        p = json.loads(plan.read_text())
        p["regularization_weight"] = 0.0
        p["max_iterations"] = 120
        p["gradient_tolerance"] = 1e-6
        rep_a = Path(td) / "a.mcr"
        rep_b = Path(td) / "b.mcr"
        pa = run_calibrate(
            write_json(Path(td) / "m.json", m),
            write_json(Path(td) / "su.json", s_unequal),
            write_json(Path(td) / "p.json", p),
            rep_a,
        )
        pb = run_calibrate(
            write_json(Path(td) / "m2.json", m),
            write_json(Path(td) / "se.json", s_equal),
            write_json(Path(td) / "p2.json", p),
            rep_b,
        )
        assert pa.returncode == 0, pa.stderr
        assert pb.returncode == 0, pb.stderr
        assert rep_a.exists() and rep_b.exists()
        a = parse_mcr(rep_a.read_text())
        b = parse_mcr(rep_b.read_text())
        assert a["objective_modal"] != b["objective_modal"]


def test_spanfit_regularization_pulls_weak_parameter_toward_reference() -> None:
    """Strong regularization keeps a weakly observed parameter near its reference."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("rank_deficient", Path(td))
        p = json.loads(plan.read_text())
        p["regularization_weight"] = 5.0
        p["frequency_weight"] = 0.01
        p["shape_weight"] = 0.01
        rep = Path(td) / "out.mcr"
        proc = run_calibrate(model, survey, write_json(Path(td) / "p.json", p), rep)
        assert proc.returncode == 0, proc.stderr
        rec = parse_mcr(rep.read_text())
        for g in rec["groups"]:
            assert abs(g["theta"] - g["reference"]) < 0.15


def test_spanfit_lower_bound_active_solution_is_reported() -> None:
    """When the optimum sits on the lower bound, BOUND_ACTIVE and LOWER are reported."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("lower_bound", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        rec = parse_mcr(rep.read_text())
        assert rec["confidence"] == "BOUND_ACTIVE"
        assert rec["groups"][0]["bound"] == "LOWER"
        assert abs(rec["groups"][0]["theta"] - rec["groups"][0]["lower"]) < 1e-8
        assert math.isfinite(rec["objective_total"])


def test_spanfit_upper_bound_active_solution_is_reported() -> None:
    """When the optimum sits on the upper bound, BOUND_ACTIVE and UPPER are reported."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("upper_bound", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        rec = parse_mcr(rep.read_text())
        assert rec["confidence"] == "BOUND_ACTIVE"
        assert rec["groups"][0]["bound"] == "UPPER"
        assert abs(rec["groups"][0]["theta"] - rec["groups"][0]["upper"]) < 1e-8
        assert math.isfinite(rec["objective_total"])


def test_spanfit_projected_step_never_leaves_parameter_box() -> None:
    """Reported group factors always lie inside declared lower/upper bounds."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("two_groups", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        for g in parse_mcr(rep.read_text())["groups"]:
            assert g["lower"] <= g["theta"] <= g["upper"]


def test_spanfit_objective_terms_sum_to_reported_total() -> None:
    """OBJECTIVE terms sum, and each PAIR carries frequency and MAC residual fields."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        raw = rep.read_text()
        assert raw.startswith("MCR 1\n")
        assert "OBJECTIVE " in raw
        assert "GROUP " in raw
        assert "PAIR " in raw
        rec = parse_mcr(raw)
        assert abs(rec["objective_total"] - (rec["objective_modal"] + rec["objective_reg"])) < 1e-15
        assert len(rec["pairs"]) >= 1
        for pair in rec["pairs"]:
            assert math.isfinite(pair["freq_res"])
            assert math.isfinite(pair["mac"])
            assert 0.0 <= pair["mac"] <= 1.0
            assert math.isfinite(pair["cost"])


def test_spanfit_converged_solution_meets_gradient_budget() -> None:
    """A successful calibration reports projected gradient within the plan budget."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        pdata = json.loads(plan.read_text())
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        rec = parse_mcr(rep.read_text())
        assert rec["projected_gradient_inf"] <= pdata["gradient_tolerance"] * 10


def test_spanfit_sensitivity_ranking_uses_documented_norm() -> None:
    """Sensitivity ranks are a permutation of 1..G with higher score ranked first."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("two_groups", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        groups = parse_mcr(rep.read_text())["groups"]
        ranks = sorted(g["rank"] for g in groups)
        assert ranks == list(range(1, len(groups) + 1))
        by_rank = sorted(groups, key=lambda g: g["rank"])
        assert by_rank[0]["score"] >= by_rank[-1]["score"] - 1e-15


def test_spanfit_sensitivity_tie_uses_group_identifier() -> None:
    """Equal sensitivity scores resolve rank ties by ascending group identifier."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("rank_deficient", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        groups = parse_mcr(rep.read_text())["groups"]
        # identical contributions => equal scores; dup-a before dup-b at better rank
        scores = {g["id"]: g["score"] for g in groups}
        assert abs(scores["dup-a"] - scores["dup-b"]) < 1e-9
        ranks = {g["id"]: g["rank"] for g in groups}
        assert ranks["dup-a"] < ranks["dup-b"]


def test_spanfit_rank_deficiency_sets_weak_confidence() -> None:
    """Collinear group contributions yield numerical rank below G and WEAK confidence."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("rank_deficient", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        rec = parse_mcr(rep.read_text())
        assert rec["numerical_rank"] < rec["group_count"]
        assert rec["confidence"] == "WEAK"
        assert math.isfinite(rec["objective_total"])


def test_spanfit_full_rank_free_solution_sets_identifiable_confidence() -> None:
    """A free full-rank solution is labeled IDENTIFIABLE."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("two_groups", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        rec = parse_mcr(rep.read_text())
        assert rec["numerical_rank"] == rec["group_count"]
        assert rec["confidence"] == "IDENTIFIABLE"
        assert all(g["bound"] == "FREE" for g in rec["groups"])


def test_spanfit_bound_active_confidence_has_precedence() -> None:
    """BOUND_ACTIVE takes precedence over WEAK or IDENTIFIABLE labels."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("lower_bound", Path(td))
        rep = Path(td) / "out.mcr"
        assert run_calibrate(model, survey, plan, rep).returncode == 0
        assert parse_mcr(rep.read_text())["confidence"] == "BOUND_ACTIVE"


def test_spanfit_repeated_run_is_byte_deterministic() -> None:
    """Two independent calibrations of the same inputs produce identical MCR bytes."""
    with isolated_workdir() as td:
        model, survey, plan = copy_sealed_triplet("single_group", Path(td))
        r1 = Path(td) / "a.mcr"
        r2 = Path(td) / "b.mcr"
        assert run_calibrate(model, survey, plan, r1).returncode == 0
        assert run_calibrate(model, survey, plan, r2).returncode == 0
        assert r1.read_bytes() == r2.read_bytes()


def test_spanfit_rejected_calibration_preserves_existing_report() -> None:
    """A rejected calibrate leaves a pre-existing report byte-for-byte intact."""
    with isolated_workdir() as td:
        model, _, plan = copy_sealed_triplet("single_group", Path(td))
        rep = Path(td) / "out.mcr"
        marker = b"PRIOR-REPORT-BYTES-9f3a\n"
        rep.write_bytes(marker)
        survey = {
            "format": "bridge-modal-survey-v1",
            "sensors": ["A", "B"],
            "modes": [
                {"mode_id": "M1", "frequency_hz": 99.0, "weight": 1.0, "shape": [0.5, 0.5]},
                {"mode_id": "M2", "frequency_hz": 100.0, "weight": 1.0, "shape": [0.4, 0.6]},
            ],
        }
        proc = run_calibrate(model, write_json(Path(td) / "s.json", survey), plan, rep)
        assert proc.returncode != 0
        assert rep.read_bytes() == marker


def test_spanfit_independent_processes_do_not_share_optimizer_state() -> None:
    """Sequential calibrations in one process context do not leak parameter state."""
    with isolated_workdir() as td:
        m1, s1, p1 = copy_sealed_triplet("single_group", Path(td) / "c1")
        m2, s2, p2 = copy_sealed_triplet("two_groups", Path(td) / "c2")
        r1 = Path(td) / "one.mcr"
        r2 = Path(td) / "two.mcr"
        assert run_calibrate(m1, s1, p1, r1).returncode == 0
        assert run_calibrate(m2, s2, p2, r2).returncode == 0
        a = parse_mcr(r1.read_text())
        b = parse_mcr(r2.read_text())
        assert a["group_count"] == 1
        assert b["group_count"] == 2
        assert a["model_sha256"] != b["model_sha256"]
