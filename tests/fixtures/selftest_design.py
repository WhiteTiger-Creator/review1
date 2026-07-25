"""Author-only design self-test for mixture-cure-standardized-fraction.

These assertions verify that the verifier's OWN model is internally discriminating: each
wrong baseline is displaced from the structural closed-form truth on the cohorts where its
bias is active, and ignoring the confounders is NOT displaced when there is nothing to
confound. None of them run the candidate, so they must NOT be part of the graded reward
(they would pass on an empty workspace). test.sh collects only tests/test_outputs.py; run
this file standalone during authoring:

    cd tests && python3 -m pytest fixtures/selftest_design.py

The wrong-baseline and cohort helpers are imported from fixtures/reference.py so this file
and the graded suite share one definition of the distractor baselines. Grading anchors on
scm.structural_truth (closed-form), and no full correct-solver lives in the verifier tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fixtures.reference as ref
from fixtures import scm


# --------------------------------------------------------------- wrong-baseline separation
def _assert_separates(baseline, active):
    named = ref.named_cohorts()
    for name in active:
        p = named[name]
        dat = scm.load_cohort(ref.data_dir(name, p))
        assert abs(baseline(dat) - scm.structural_truth(p)) >= scm.NAIVE_MIN_ABS, name


def test_wrong_fg_only_fails():
    """Ignoring the continuous baseline confounder misses the truth wherever it is active."""
    _assert_separates(ref.wb_fg_only, ref.WB_FG_ONLY_ACTIVE)


def test_wrong_c_only_fails():
    """Adjusting for the continuous confounder but skipping the (F,G) standardization misses
    the truth wherever binary-flag confounding is active."""
    _assert_separates(ref.wb_c_only, ref.WB_C_ONLY_ACTIVE)


def test_wrong_linear_c_prop_fails():
    """Entering the continuous index linearly in the propensity (no curvature) leaves
    residual confounding wherever assignment bends in the index."""
    _assert_separates(ref.wb_linear_c_prop, ref.WB_LINEAR_C_ACTIVE)


def test_wrong_km_interior_fails():
    """Reading the survival curve at an interior time rather than the plateau misses the
    truth on cohorts with a real effect."""
    _assert_separates(ref.wb_km_interior, ref.WB_INTERIOR_ACTIVE)


def test_wrong_landmark_complete_case_fails():
    """Counting not-yet-relapsed susceptibles as long-term event-free misses the truth on
    cohorts with a real effect."""
    _assert_separates(ref.wb_landmark_complete_case, ref.WB_LANDMARK_ACTIVE)


# --------------------------------------------------------------- not-displaced sanity checks
def test_fg_only_ok_without_c_confounding():
    """When the continuous index does not confound assignment, ignoring it is NOT displaced,
    confirming the fg-only separation above is driven by continuous confounding."""
    p = scm.HIDDEN["h_no_c_confound"]
    dat = scm.load_cohort(ref.stage(p))
    assert abs(ref.wb_fg_only(dat) - scm.structural_truth(p)) < scm.NAIVE_MIN_ABS


def test_fg_only_ok_without_any_confounding():
    """With no confounding at all, ignoring the confounders is not displaced either."""
    p = scm.HIDDEN["h_no_confound"]
    dat = scm.load_cohort(ref.stage(p))
    assert abs(ref.wb_fg_only(dat) - scm.structural_truth(p)) < scm.NAIVE_MIN_ABS
