"""Graded verifier for mixture-cure-standardized-fraction.

Every test in this file runs the candidate's analysis.R and grades its estimate.json. The
candidate is compared against an independent oracle (propensity-weighted Kaplan-Meier
plateau standardized over the (stage_high, marker_high) mix) recomputed from the same raw
records, on the committed cohort and many held-back cohorts. On the cohorts where a given
shortcut is biased, the candidate must not only match the oracle but also sit clear of the
corresponding wrong baseline (ignore the continuous confounder, drop the binary-flag
standardization, read the curve before the plateau, or count censored susceptibles as
long-term event-free). Metamorphic relations (time rescale, permutation,
latency shape, baseline shift and scale) must leave the candidate's estimate invariant, and
three repeat runs must be byte-identical.

The oracle and wrong-baseline definitions live in fixtures/reference.py; the design
assertions that check the verifier's own model is internally discriminating (and do not run
the candidate) live in fixtures/selftest_design.py and are NOT collected for reward.
"""

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures.reference as ref
from fixtures import scm

APP = "/app"
ANALYSIS = os.path.join(APP, "analysis.R")
ESTIMATE = os.path.join(APP, "estimate.json")
COMMITTED_DIR = os.path.join(APP, "data")


# --------------------------------------------------------------- candidate runner
# The candidate is re-run against many cohorts, and several cohorts recur across the accuracy,
# wrong-baseline, and metamorphic tests (the committed cohort alone appears in a dozen). The
# staged cohorts are deterministic — the same cohort seed writes byte-identical CSVs on every
# staging — so a run keyed on the data-directory content is reproducible: caching returns the
# same number a re-run would, and only removes redundant executions. The determinism test
# opts out (use_cache=False) so it still forces three real runs.
_CACHE = {}


def _data_key(data_dir):
    h = hashlib.sha256()
    for fn in ("enrollment.csv", "followup.csv", "site_calendar.csv"):
        with open(os.path.join(data_dir, fn), "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    return h.hexdigest()


def _run_candidate(data_dir, use_cache=True):
    if use_cache:
        key = _data_key(data_dir)
        if key in _CACHE:
            return _CACHE[key]
    if os.path.exists(ESTIMATE):
        os.remove(ESTIMATE)
    env = dict(os.environ, CAUSAL_DATA_DIR=data_dir)
    r = subprocess.run(
        ["Rscript", ANALYSIS],
        cwd=APP,
        env=env,
        capture_output=True,
        text=True,
        timeout=1200,
        check=False,
    )
    assert r.returncode == 0, f"analysis.R failed:\n{r.stderr}"
    with open(ESTIMATE) as fh:
        est = float(json.load(fh)["estimate"])
    if use_cache:
        _CACHE[key] = est
    return est


# --------------------------------------------------------------- preconditions (zero credit)
def test_analysis_exists():
    """The candidate produced an R program at the disclosed path."""
    assert os.path.exists(ANALYSIS)


def test_output_schema():
    """estimate.json carries a single finite numeric estimate in the plausible range."""
    est = _run_candidate(COMMITTED_DIR)
    assert math.isfinite(est) and -1.0 <= est <= 1.0


def test_no_forbidden_access():
    """The candidate source reads the disclosed data and never the verifier tree."""
    with open(ANALYSIS) as fh:
        src = fh.read()
    assert "/tests" not in src and "fixtures" not in src
    assert any(tok in src for tok in ("CAUSAL_DATA_DIR", "read.csv", "list.files"))


def test_estimate_is_recomputed_not_hardcoded():
    """The estimate differs between the committed cohort and a null-effect cohort, so a
    hardcoded constant cannot pass."""
    committed = _run_candidate(COMMITTED_DIR)
    null_est = _run_candidate(ref.stage(scm.HIDDEN["h_null"]))
    assert abs(committed - null_est) > 1e-6


# --------------------------------------------------------------- candidate accuracy
_ACCURACY_COHORTS = list(ref.named_cohorts().items())


@pytest.mark.parametrize(
    "name,params", _ACCURACY_COHORTS, ids=[n for n, _ in _ACCURACY_COHORTS]
)
def test_candidate_matches_truth(name, params):
    """On the committed cohort and every held-back cohort the candidate agrees with the
    independent closed-form structural cure-fraction contrast for that cohort. The truth is
    derived from the generating parameters (the structural cure logit integrated over the
    baseline-index distribution), not from a second run of the estimator, so passing does
    not depend on reproducing any one estimator's implementation."""
    data_dir = ref.data_dir(name, params)
    est = _run_candidate(data_dir)
    assert abs(est - scm.structural_truth(params)) <= scm.TRUTH_ABS_TOL, name


# --------------------------------------------------------------- wrong-baseline separation
# Each case runs the candidate and checks it both agrees with the independent closed-form
# structural truth AND is displaced from the named wrong baseline on a cohort where that
# baseline's bias is active. A candidate that took the shortcut lands on the wrong baseline
# and fails. Correctness is graded against the documented estimand (structural_truth), the
# same standard as test_candidate_matches_truth, not against any one estimator's realized
# value; the baseline value is only a distractor the candidate must stay clear of.
def _assert_candidate_beats(name, baseline):
    named = ref.named_cohorts()
    params = named[name]
    data_dir = ref.data_dir(name, params)
    dat = scm.load_cohort(data_dir)
    est = _run_candidate(data_dir)
    assert abs(est - scm.structural_truth(params)) <= scm.TRUTH_ABS_TOL, (
        f"{name}: off truth"
    )
    assert abs(est - baseline(dat)) >= scm.NAIVE_MIN_ABS, (
        f"{name}: not clear of baseline"
    )


@pytest.mark.parametrize("name", ref.BIND_FG_ONLY)
def test_candidate_beats_fg_only(name):
    """Where the continuous baseline index confounds assignment, the candidate must adjust
    for it — landing clear of the (F,G)-only plateau that ignores the continuous confounder."""
    _assert_candidate_beats(name, ref.wb_fg_only)


@pytest.mark.parametrize("name", ref.BIND_C_ONLY)
def test_candidate_beats_c_only(name):
    """The candidate must standardize over the registry (F,G) mix, not just balance the
    continuous index and pool the arms. With a stage-by-marker interaction in the cure
    structure the four flag cells are non-additive, so the c-only shortcut (inverse-weight
    the continuous index, skip the (F,G) standardization) lands clear of the truth; the
    candidate must sit with the truth and away from that shortcut."""
    _assert_candidate_beats(name, ref.wb_c_only)


@pytest.mark.parametrize("name", ref.BIND_INTERIOR)
def test_candidate_beats_km_interior(name):
    """The candidate must read the plateau, not an interior horizon — landing clear of the
    survival read at LANDMARK that counts not-yet-relapsed susceptibles as event-free."""
    _assert_candidate_beats(name, ref.wb_km_interior)


@pytest.mark.parametrize("name", ref.BIND_LANDMARK)
def test_candidate_beats_landmark_complete_case(name):
    """The candidate must use risk-set estimation, not a complete-case landmark proportion —
    landing clear of the estimate that conflates latency with cure and ignores censoring."""
    _assert_candidate_beats(name, ref.wb_landmark_complete_case)


# --------------------------------------------------------------- metamorphic relations
META_COHORTS = [
    "committed",
    "h_strong_effect",
    "h_strong_c",
    "h_nonlin_assign",
    "h_strong_fg",
    "h_combo",
    "h_big_n",
    "h_high_cure",
]


def _copy_rows(path):
    import csv as _csv

    with open(path) as fh:
        return list(_csv.reader(fh))


def _rescaled_dir(src_dir, k):
    import csv as _csv

    dst = tempfile.mkdtemp(prefix="meta_scale_")
    with open(os.path.join(src_dir, "followup.csv")) as fh:
        rows = list(_csv.DictReader(fh))
    with open(os.path.join(dst, "followup.csv"), "w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["patient_id", "months_observed", "outcome"])
        for r in rows:
            w.writerow(
                [
                    r["patient_id"],
                    round(float(r["months_observed"]) * k, 6),
                    r["outcome"],
                ]
            )
    for fn in ("enrollment.csv", "site_calendar.csv"):
        rows = _copy_rows(os.path.join(src_dir, fn))
        # scale every calendar time by k so the documented administrative window
        # (site cutoff minus enrolment month) rescales consistently: enrolment
        # month is column 2 of enrollment.csv, the cutoff is column 1 of
        # site_calendar.csv
        col = 2 if fn == "enrollment.csv" else 1
        for i in range(1, len(rows)):
            rows[i][col] = str(round(float(rows[i][col]) * k, 6))
        with open(os.path.join(dst, fn), "w", newline="") as fh:
            _csv.writer(fh).writerows(rows)
    return dst


def _permuted_dir(src_dir, seed):
    import csv as _csv

    dst = tempfile.mkdtemp(prefix="meta_perm_")
    rng = np.random.RandomState(seed)
    with open(os.path.join(src_dir, "enrollment.csv")) as fh:
        enr = list(_csv.DictReader(fh))
    with open(os.path.join(src_dir, "followup.csv")) as fh:
        fol = {r["patient_id"]: r for r in _csv.DictReader(fh)}
    relabel = {r["patient_id"]: f"Q{i:06d}" for i, r in enumerate(enr)}
    order = list(range(len(enr)))
    rng.shuffle(order)
    with open(os.path.join(dst, "enrollment.csv"), "w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(
            [
                "patient_id",
                "site_id",
                "enroll_month",
                "therapy",
                "stage_high",
                "marker_high",
                "baseline_index",
            ]
        )
        for i in order:
            r = enr[i]
            w.writerow(
                [
                    relabel[r["patient_id"]],
                    r["site_id"],
                    r["enroll_month"],
                    r["therapy"],
                    r["stage_high"],
                    r["marker_high"],
                    r["baseline_index"],
                ]
            )
    order2 = list(range(len(enr)))
    rng.shuffle(order2)
    with open(os.path.join(dst, "followup.csv"), "w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["patient_id", "months_observed", "outcome"])
        for i in order2:
            r = fol[enr[i]["patient_id"]]
            w.writerow(
                [relabel[enr[i]["patient_id"]], r["months_observed"], r["outcome"]]
            )
    import shutil

    shutil.copy(
        os.path.join(src_dir, "site_calendar.csv"),
        os.path.join(dst, "site_calendar.csv"),
    )
    return dst


def _transform_baseline_index(src_dir, fn):
    import csv as _csv

    dst = tempfile.mkdtemp(prefix="meta_c_")
    with open(os.path.join(src_dir, "enrollment.csv")) as fh:
        rows = list(_csv.DictReader(fh))
    with open(os.path.join(dst, "enrollment.csv"), "w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(
            [
                "patient_id",
                "site_id",
                "enroll_month",
                "therapy",
                "stage_high",
                "marker_high",
                "baseline_index",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r["patient_id"],
                    r["site_id"],
                    r["enroll_month"],
                    r["therapy"],
                    r["stage_high"],
                    r["marker_high"],
                    round(fn(float(r["baseline_index"])), 6),
                ]
            )
    import shutil

    for f in ("followup.csv", "site_calendar.csv"):
        shutil.copy(os.path.join(src_dir, f), os.path.join(dst, f))
    return dst


def _latency_regen_dir(params):
    return ref.stage(dict(params, beta_a=1.0, beta_b=1.0))


@pytest.mark.parametrize("name", META_COHORTS[:6])
def test_metamorphic_time_rescale(name):
    """Scaling every recorded time by a constant -- enrolment month, follow-up time,
    and the site administrative cutoff together, so the administrative window is
    preserved -- leaves the plateau-based estimate unchanged."""
    p = ref.named_cohorts()[name]
    base_dir = ref.data_dir(name, p)
    assert (
        abs(_run_candidate(base_dir) - _run_candidate(_rescaled_dir(base_dir, 4.0)))
        <= scm.META_EXACT_TOL
    ), name


@pytest.mark.parametrize(
    "i,name", list(enumerate(META_COHORTS[:6])), ids=META_COHORTS[:6]
)
def test_metamorphic_permutation(i, name):
    """Shuffling rows and relabeling patient ids leaves the estimate unchanged."""
    p = ref.named_cohorts()[name]
    base_dir = ref.data_dir(name, p)
    assert (
        abs(
            _run_candidate(base_dir) - _run_candidate(_permuted_dir(base_dir, 7000 + i))
        )
        <= scm.META_EXACT_TOL
    ), name


@pytest.mark.parametrize("name", ["committed", "h_strong_effect", "h_high_cure"])
def test_metamorphic_latency_shape(name):
    """Changing only the susceptible latency shape (same cure and censoring) leaves the
    cure-fraction estimate invariant, confirming incidence is separated from latency."""
    p = ref.named_cohorts()[name]
    base = _run_candidate(ref.data_dir(name, p))
    assert abs(base - _run_candidate(_latency_regen_dir(p))) <= scm.META_LATENCY_TOL, (
        name
    )


@pytest.mark.parametrize("name", ["committed", "h_strong_c", "h_big_n"])
def test_metamorphic_baseline_shift(name):
    """Shifting the baseline index by a constant leaves the estimate invariant (a correct
    covariate adjustment absorbs an affine reparameterization; a hardcoded threshold does not)."""
    p = ref.named_cohorts()[name]
    base_dir = ref.data_dir(name, p)
    base = _run_candidate(base_dir)
    shifted = _run_candidate(_transform_baseline_index(base_dir, lambda c: c + 2.0))
    assert abs(base - shifted) <= scm.META_LATENCY_TOL, name


@pytest.mark.parametrize("name", ["committed", "h_strong_c", "h_high_cure"])
def test_metamorphic_baseline_scale(name):
    """Rescaling the baseline index by a constant leaves the estimate invariant, rejecting
    solvers that threshold the index at a hardcoded value."""
    p = ref.named_cohorts()[name]
    base_dir = ref.data_dir(name, p)
    base = _run_candidate(base_dir)
    scaled = _run_candidate(_transform_baseline_index(base_dir, lambda c: c * 1.5))
    assert abs(base - scaled) <= scm.META_LATENCY_TOL, name


# --------------------------------------------------------------- determinism
def test_deterministic_over_three_runs():
    """Three runs on the committed cohort produce identical estimate.json bytes."""
    outs = []
    for _ in range(3):
        _run_candidate(COMMITTED_DIR, use_cache=False)
        with open(ESTIMATE) as fh:
            outs.append(fh.read())
    assert outs[0] == outs[1] == outs[2]
