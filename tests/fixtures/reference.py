"""Verifier-side reference distractors for mixture-cure-standardized-fraction.

Holds the four wrong baselines (deliberately-biased estimators the candidate must stay
clear of) and the cohort-staging helpers. Both the graded suite (tests/test_outputs.py)
and the author-only design self-test (fixtures/selftest_design.py) import these. Grading
anchors correctness on the closed-form structural truth (scm.structural_truth), which is
derived from the generating parameters and runs no estimator, so no full correct-solver for
the task lives in the verifier tree; the helpers below build only the wrong baselines.
Nothing here runs the candidate.
"""

import os
import tempfile

import numpy as np
from fixtures import scm

APP = "/app"


# --------------------------------------------------------------- KM helpers
def km_plateau(times, events, w=None):
    """Weighted Kaplan-Meier survival after the last observed event (the plateau)."""
    if w is None:
        w = np.ones_like(times, dtype=float)
    order = np.argsort(times, kind="mergesort")
    t, e, w = np.asarray(times)[order], np.asarray(events)[order], np.asarray(w)[order]
    n = len(t)
    surv = 1.0
    at_risk = w.sum()
    i = 0
    while i < n:
        tk = t[i]
        j = i
        d = 0.0
        while j < n and t[j] == tk:
            if e[j] == 1:
                d += w[j]
            j += 1
        if d > 0 and at_risk > 0:
            surv *= 1.0 - d / at_risk
        at_risk -= w[i:j].sum()
        i = j
    return surv


def km_survival_at(times, events, horizon, w=None):
    """Weighted Kaplan-Meier survival at an interior horizon (for a wrong baseline)."""
    if w is None:
        w = np.ones_like(times, dtype=float)
    order = np.argsort(times, kind="mergesort")
    t, e, w = np.asarray(times)[order], np.asarray(events)[order], np.asarray(w)[order]
    n = len(t)
    surv = 1.0
    at_risk = w.sum()
    i = 0
    while i < n and t[i] <= horizon:
        tk = t[i]
        j = i
        d = 0.0
        while j < n and t[j] == tk:
            if e[j] == 1:
                d += w[j]
            j += 1
        if d > 0 and at_risk > 0:
            surv *= 1.0 - d / at_risk
        at_risk -= w[i:j].sum()
        i = j
    return surv


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def ipw_weights(dat, design):
    """Inverse-probability-of-treatment weights from a logistic propensity fit by IRLS on
    the given design columns, with symmetric truncation."""
    n = len(dat["A"])
    X = np.column_stack([np.ones(n), *design])
    beta = np.zeros(X.shape[1])
    y = dat["A"].astype(float)
    for _ in range(60):
        eta = X @ beta
        mu = _expit(eta)
        W = np.clip(mu * (1 - mu), 1e-9, None)
        z = eta + (y - mu) / W
        XtW = X.T * W
        beta = np.linalg.solve(XtW @ X, XtW @ z)
    e = np.clip(_expit(X @ beta), scm.PROP_TRUNC, 1 - scm.PROP_TRUNC)
    return np.where(dat["A"] == 1, 1.0 / e, 1.0 / (1.0 - e))


def standardize_fg(dat, per_stratum):
    """Standardize a per-stratum statistic over the empirical (F,G) mix; arm difference."""
    out = {}
    for a in (0, 1):
        acc = 0.0
        for f in (0, 1):
            for g in (0, 1):
                w = np.mean((dat["F"] == f) & (dat["G"] == g))
                idx = (dat["F"] == f) & (dat["G"] == g) & (dat["A"] == a)
                if idx.sum() < 5:
                    continue
                acc += w * per_stratum(idx)
        out[a] = acc
    return out[1] - out[0]


# Grading anchors on the closed-form structural truth (scm.structural_truth), which is
# derived from the generating parameters and never runs an estimator, so no full solver
# for the task lives in the verifier. The helpers below (ipw_weights, km_plateau,
# standardize_fg) build only the deliberately-wrong baselines used as distractors.


# --------------------------------------------------------------- wrong baselines
def wb_fg_only(dat):
    """Ignore the continuous confounder: plain KM plateau standardized over (F,G) only."""
    return standardize_fg(
        dat, lambda idx: km_plateau(dat["months"][idx], dat["event"][idx])
    )


def wb_c_only(dat):
    """Adjust for C by IPW but skip the (F,G) standardization (pool arms directly)."""
    w = ipw_weights(dat, [dat["C"], dat["C"] ** 2])
    out = {}
    for a in (0, 1):
        idx = dat["A"] == a
        out[a] = km_plateau(dat["months"][idx], dat["event"][idx], w[idx])
    return out[1] - out[0]


def wb_linear_c_prop(dat):
    """Adjust for the continuous confounder but enter it LINEARLY in the propensity (no
    curvature), then standardize over (F,G). Because assignment bends in the index, this
    leaves residual confounding wherever the curvature is active."""
    w = ipw_weights(dat, [dat["F"], dat["G"], dat["C"]])
    return standardize_fg(
        dat, lambda idx: km_plateau(dat["months"][idx], dat["event"][idx], w[idx])
    )


def wb_km_interior(dat):
    """Correct weighting and standardization but read the curve at an interior time rather
    than the plateau, counting not-yet-relapsed susceptibles as long-term event-free."""
    w = ipw_weights(dat, [dat["F"], dat["G"], dat["C"], dat["C"] ** 2])
    return standardize_fg(
        dat,
        lambda idx: km_survival_at(
            dat["months"][idx], dat["event"][idx], scm.LANDMARK, w[idx]
        ),
    )


def wb_landmark_complete_case(dat):
    """Event-free proportion at an interior landmark among patients followed at least that
    long, standardized over (F,G); conflates latency with cure and ignores censoring."""
    vals = {}
    for a in (0, 1):
        acc, wsum = 0.0, 0.0
        for f in (0, 1):
            for g in (0, 1):
                idx = (
                    (dat["F"] == f)
                    & (dat["G"] == g)
                    & (dat["A"] == a)
                    & (dat["months"] >= scm.LANDMARK)
                )
                if idx.sum() < 5:
                    continue
                w = np.mean((dat["F"] == f) & (dat["G"] == g))
                ef = np.mean(
                    (dat["event"][idx] == 0) | (dat["months"][idx] > scm.LANDMARK)
                )
                acc += w * ef
                wsum += w
        vals[a] = acc / wsum if wsum else float("nan")
    return vals[1] - vals[0]


# cohorts on which each baseline's bias is active (|baseline - structural truth| >=
# NAIVE_MIN_ABS), from the deterministic separation calibration. Used by the author-only
# design self-test to confirm each shortcut is genuinely biased where claimed.
WB_FG_ONLY_ACTIVE = [
    "committed", "h_null", "h_strong_effect", "h_reverse_effect", "h_strong_confound",
    "h_strong_c", "h_nonlinear_c", "h_light_effect", "h_big_n", "h_small_n",
    "h_light_dropout", "h_mid_confound", "h_high_cure", "h_low_cure", "h_wide_entry",
    "h_alt_cutoff", "h_combo", "h_nonlin_assign", "h_strong_fg",
]
WB_C_ONLY_ACTIVE = [
    "committed", "h_null", "h_no_c_confound", "h_strong_effect", "h_reverse_effect",
    "h_strong_confound", "h_strong_c", "h_nonlinear_c", "h_light_effect", "h_big_n",
    "h_small_n", "h_light_dropout", "h_mid_confound", "h_high_cure", "h_low_cure",
    "h_wide_entry", "h_alt_cutoff", "h_combo", "h_nonlin_assign", "h_strong_fg",
]
WB_LINEAR_C_ACTIVE = ["h_strong_c", "h_high_cure", "h_alt_cutoff", "h_nonlin_assign"]
WB_INTERIOR_ACTIVE = [
    "committed", "h_no_confound", "h_no_c_confound", "h_strong_effect", "h_reverse_effect",
    "h_strong_c", "h_nonlinear_c", "h_light_effect", "h_big_n", "h_small_n",
    "h_light_dropout", "h_mid_confound", "h_high_cure", "h_low_cure", "h_wide_entry",
    "h_alt_cutoff", "h_combo", "h_nonlin_assign", "h_strong_fg",
]
WB_LANDMARK_ACTIVE = [
    "committed", "h_no_confound", "h_no_c_confound", "h_strong_effect", "h_reverse_effect",
    "h_strong_confound", "h_strong_c", "h_nonlinear_c", "h_light_effect", "h_big_n",
    "h_small_n", "h_light_dropout", "h_mid_confound", "h_high_cure", "h_low_cure",
    "h_wide_entry", "h_alt_cutoff", "h_combo", "h_nonlin_assign", "h_strong_fg",
]

# Cohorts used by the GRADED candidate-vs-baseline bind tests. A graded bind requires the
# candidate to be within TRUTH_ABS_TOL of the closed-form structural truth AND at least
# NAIVE_MIN_ABS from the baseline. Whenever the baseline sits at least
# NAIVE_MIN_ABS + TRUTH_ABS_TOL = 0.11 from the truth, any candidate that passes the
# accuracy test is guaranteed (triangle inequality) to clear the baseline, so these lists
# only ever fail a candidate that is already wrong -- never a correct-but-different one.
# All entries below were verified at the >= 0.11 headroom on the regenerated cohorts.
#
# The stage-by-marker interaction and the curved continuous confounder now push the
# skip-(F,G)-standardization shortcut past the headroom, so c_only is a graded bind. The
# linear-in-index propensity shortcut (wb_linear_c_prop) stays below 0.11 and is graded
# indirectly: its bias exceeds TRUTH_ABS_TOL on the curved-assignment cohorts, so a
# candidate that takes it fails test_candidate_matches_truth there.
BIND_FG_ONLY = [
    "h_null", "h_strong_effect", "h_reverse_effect", "h_strong_c", "h_light_effect",
    "h_big_n", "h_small_n", "h_light_dropout", "h_high_cure", "h_wide_entry",
    "h_alt_cutoff", "h_combo", "h_nonlin_assign", "h_strong_fg",
]
BIND_C_ONLY = [
    "h_strong_effect", "h_reverse_effect", "h_strong_confound", "h_strong_c", "h_small_n",
    "h_light_dropout", "h_high_cure", "h_wide_entry", "h_alt_cutoff", "h_combo",
    "h_nonlin_assign", "h_strong_fg",
]
BIND_INTERIOR = ["h_strong_effect", "h_strong_fg"]
BIND_LANDMARK = [
    "committed", "h_no_confound", "h_no_c_confound", "h_strong_effect", "h_strong_confound",
    "h_strong_c", "h_nonlinear_c", "h_big_n", "h_small_n", "h_light_dropout",
    "h_mid_confound", "h_high_cure", "h_low_cure", "h_wide_entry", "h_alt_cutoff",
    "h_nonlin_assign", "h_strong_fg",
]


# --------------------------------------------------------------- cohort staging
def named_cohorts():
    out = {"committed": scm.COMMITTED}
    out.update(scm.HIDDEN)
    return out


def stage(params):
    d = tempfile.mkdtemp(prefix="cohort_")
    scm.write_cohort(params, d)
    return d


def data_dir(name, params):
    """Committed cohort is the disclosed /app/data; every hidden cohort is staged fresh."""
    return os.path.join(APP, "data") if name == "committed" else stage(params)
