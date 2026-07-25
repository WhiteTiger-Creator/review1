"""Verifier-owned structural causal model for the mixture-cure cohort.

Holds the held-back structural constants, generates deterministic cohorts, and
writes the candidate-visible CSV bundle. The committed sample under
environment/data/ is produced from COMMITTED; the verifier regenerates hidden
cohorts from held-back seeds. The structural cure fractions are known in closed
form, so the true standardized contrast never has to be read from a stored file.

Cohort mechanism: two binary baseline flags F (stage_high) and G (marker_high)
and a continuous baseline index C drive both confounded therapy uptake and the
cure probability; C enters the cure logit nonlinearly (a quadratic term), so
adjusting for it cannot be reduced to the binary-flag cells. A patient is "cured"
(never relapses) with probability pi_a(F,G,C) under therapy world a; susceptible
patients relapse on a bounded latency support so that, with enough follow-up, the
survival curve reaches a plateau equal to the cure fraction. Administrative
follow-up (staggered entry, per-site cutoff) plus independent loss-to-follow-up
censor some susceptibles before they relapse, so risk-set estimation is required
and a raw event-free proportion is biased.
"""

import csv
import math
import os

import numpy as np

# fixed 64-node Gauss-Hermite rule for the probabilists' weight exp(-x^2/2)/sqrt(2pi),
# used to integrate the continuous baseline index C out of the structural cure fraction
_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(64)
_GH_W = _GH_W / math.sqrt(2.0 * math.pi)

THERAPY_LABEL = {1: "newer", 0: "standard"}
OUTCOME_LABEL = {1: "relapse", 0: "censored"}
LABEL_THERAPY = {v: k for k, v in THERAPY_LABEL.items()}
LABEL_OUTCOME = {v: k for k, v in OUTCOME_LABEL.items()}

# grading constants derived from the sampling-error analysis in the design dossier
CANDIDATE_ABS_TOL = 0.025  # candidate vs independent oracle on identical data
TRUTH_BAND = (
    0.05  # oracle recomputation vs structural truth (IPW finite-sample variance)
)
TRUTH_ABS_TOL = 0.06  # graded candidate vs closed-form structural truth: the
# worst oracle-to-truth finite-sample gap observed across cohorts and seeds is
# ~0.042, and the candidate carries its own comparable estimation error, so the
# band admits any consistent estimator of the documented estimand while still
# rejecting a wrong or hardcoded answer
NAIVE_MIN_ABS = 0.05  # required displacement of an active wrong baseline
META_EXACT_TOL = 1e-7  # exact metamorphic invariances (row permutation, time rescale):
# the risk-set / plateau estimand is exactly invariant to both (a row reorder is
# bit-identical, and scaling every recorded time preserves event ordering and censoring),
# so the oracle clears this with orders of magnitude to spare. The band is set at 1e-7
# rather than machine-epsilon so it rejects scale-DEPENDENT parametric fits, whose
# optimizer path drifts by ~1e-6 when the time axis is rescaled, while never flaking the
# scale-free reading.
META_LATENCY_TOL = 0.025  # latency-shape / covariate-shift invariance (finite sample)
PROP_TRUNC = 0.02  # symmetric propensity-weight truncation bound
LANDMARK = 18.0  # interior time used by two wrong baselines
LONG_HORIZON = 40.0  # a time strictly beyond every susceptible support cap

_BASE = {
    "n": 9000,
    "pF": 0.45,
    "pG": 0.40,
    "a0": 0.10,
    "aF": -0.85,
    "aG": -0.70,
    "aFG": -0.75,  # stage-by-marker interaction in the cure logit: the four flag cells
    # are non-additive, so pooling arms without standardizing over the (F,G) mix is biased
    "aA": 0.75,
    "aC": -0.90,
    "aC2": -0.30,
    "g0": -0.30,
    "gF": 1.35,
    "gG": 1.05,
    "gC": 1.10,
    "gC2": 0.45,  # curvature of the continuous confounder in the assignment logit: a
    # propensity model linear in the index is misspecified and leaves residual confounding
    "smax": 36.0,
    "beta_a": 2.0,
    "beta_b": 2.0,
    "site_cutoffs": (72.0, 78.0, 66.0),
    "enroll_span": 24,
    "d_scale": 60.0,
}


def _params(**over):
    p = dict(_BASE)
    p.update(over)
    return p


# committed sample the agent sees under environment/data/
COMMITTED = _params(seed=42)

# held-back cohorts the agent never sees; regenerated at verify time from seeds.
# effect includes the exact null and a negative effect; confounding, dropout, and
# sample size vary so no memorized constant generalizes.
HIDDEN = {
    "h_null": _params(aA=0.0, seed=101),
    "h_no_confound": _params(gF=0.0, gG=0.0, gC=0.0, gC2=0.0, seed=102),
    "h_no_c_confound": _params(gC=0.0, gC2=0.0, seed=116),
    "h_strong_effect": _params(aA=1.10, seed=103),
    "h_reverse_effect": _params(aA=-0.50, seed=104),
    "h_strong_confound": _params(gF=1.60, gG=1.40, seed=105),
    "h_strong_c": _params(gC=1.80, seed=117),
    "h_nonlinear_c": _params(aC2=-0.60, seed=118),
    "h_light_effect": _params(aA=0.40, seed=106),
    "h_big_n": _params(n=12000, seed=107),
    "h_small_n": _params(n=5000, seed=108),
    "h_light_dropout": _params(d_scale=90.0, seed=109),
    "h_mid_confound": _params(gF=0.80, gG=0.65, gC=0.70, seed=110),
    "h_high_cure": _params(a0=0.70, seed=111),
    "h_low_cure": _params(a0=-0.60, seed=112),
    "h_wide_entry": _params(enroll_span=30, seed=113),
    "h_alt_cutoff": _params(site_cutoffs=(60.0, 84.0, 70.0), seed=114),
    "h_combo": _params(aA=0.55, gF=1.5, gG=1.2, gC=1.5, n=10000, seed=115),
    # curved continuous confounding in assignment: a propensity linear in the index
    # leaves strong residual confounding here
    "h_nonlin_assign": _params(gC2=1.30, gC=1.40, seed=119),
    # strong stage/marker confounding with a large flag interaction: pooling arms
    # without standardizing over the registry (F,G) mix is heavily biased here
    "h_strong_fg": _params(gF=1.85, gG=1.55, aFG=-1.15, seed=120),
}


def _expit(x):
    return 1.0 / (1.0 + math.exp(-x))


def structural_truth(p):
    """Standardized cure-fraction difference E_X[pi_1(X) - pi_0(X)] over the joint
    distribution of the two independent binary flags and the standard-normal baseline
    index C. The binary flags are summed over their marginals; C is integrated out by a
    fixed 64-node Gauss-Hermite rule. C enters the cure logit as aC*C + aC2*C^2, so the
    contrast is not a plain 4-cell average."""
    total = 0.0
    for f in (0, 1):
        for g in (0, 1):
            w = (p["pF"] if f else 1 - p["pF"]) * (p["pG"] if g else 1 - p["pG"])
            lin = (
                p["a0"]
                + p["aF"] * f
                + p["aG"] * g
                + p["aFG"] * f * g
                + p["aC"] * _GH_X
                + p["aC2"] * _GH_X**2
            )
            pi1 = float(np.sum(_GH_W / (1.0 + np.exp(-(lin + p["aA"])))))
            pi0 = float(np.sum(_GH_W / (1.0 + np.exp(-lin))))
            total += w * (pi1 - pi0)
    return total


def _substream(seed, offset):
    return np.random.RandomState((seed * 97 + offset) % (2**32))


def simulate(p):
    """Return the latent + observed arrays for one cohort as plain Python lists.

    Each component draws from an independent seeded substream, so changing the latency
    shape (beta_a, beta_b) leaves the covariates, assignment, cure indicators, and
    censoring draws untouched. That keeps the latency metamorphism a clean
    incidence-vs-latency comparison rather than perturbing the whole cohort."""
    n = p["n"]
    cutoffs = list(p["site_cutoffs"])
    nsite = len(cutoffs)

    cov = _substream(p["seed"], 1)
    F = (cov.random_sample(n) < p["pF"]).astype(int)
    G = (cov.random_sample(n) < p["pG"]).astype(int)
    site = cov.randint(0, nsite, size=n)
    enroll = cov.randint(0, p["enroll_span"] + 1, size=n).astype(float)
    cutoff = np.array([cutoffs[s] for s in site])
    c_admin = cutoff - enroll

    # continuous baseline index C on its own substream so it perturbs nothing else
    C = _substream(p["seed"], 6).standard_normal(n)

    assign = _substream(p["seed"], 2)
    prop = np.array(
        [
            _expit(
                p["g0"]
                + p["gF"] * F[i]
                + p["gG"] * G[i]
                + p["gC"] * C[i]
                + p["gC2"] * C[i] ** 2
            )
            for i in range(n)
        ]
    )
    A = (assign.random_sample(n) < prop).astype(int)

    cure_rng = _substream(p["seed"], 3)
    p_cure = np.array(
        [
            _expit(
                p["a0"]
                + p["aF"] * F[i]
                + p["aG"] * G[i]
                + p["aFG"] * F[i] * G[i]
                + p["aC"] * C[i]
                + p["aC2"] * C[i] ** 2
                + p["aA"] * A[i]
            )
            for i in range(n)
        ]
    )
    cured = (cure_rng.random_sample(n) < p_cure).astype(int)

    latency = _substream(p["seed"], 4)
    relapse_time = p["smax"] * latency.beta(p["beta_a"], p["beta_b"], size=n)
    relapse_time[cured == 1] = np.inf

    drop_rng = _substream(p["seed"], 5)
    dropout = drop_rng.exponential(scale=p["d_scale"], size=n)
    cens_time = np.minimum(c_admin, dropout)
    relapse_obs = (relapse_time <= cens_time).astype(int)
    months = np.where(relapse_obs == 1, relapse_time, cens_time)
    event = relapse_obs

    return {
        "patient_id": [f"P{p['seed']:04d}{i:05d}" for i in range(n)],
        "site_id": (site + 1).tolist(),
        "enroll_month": enroll.tolist(),
        "cutoff": cutoff.tolist(),
        "therapy": A.tolist(),
        "stage_high": F.tolist(),
        "marker_high": G.tolist(),
        "baseline_index": [round(float(c), 6) for c in C],
        "months_observed": [round(float(m), 6) for m in months],
        "event": event.tolist(),
        "smax": p["smax"],
        "relapse_time": relapse_time,  # latent; used only by the latency metamorphism
        "cured": cured.tolist(),
    }


def write_cohort(p, out_dir):
    """Write the candidate-visible three-file bundle for one cohort to out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    d = simulate(p)
    n = len(d["patient_id"])

    with open(os.path.join(out_dir, "enrollment.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
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
        for i in range(n):
            w.writerow(
                [
                    d["patient_id"][i],
                    d["site_id"][i],
                    int(d["enroll_month"][i]),
                    THERAPY_LABEL[d["therapy"][i]],
                    d["stage_high"][i],
                    d["marker_high"][i],
                    d["baseline_index"][i],
                ]
            )

    with open(os.path.join(out_dir, "followup.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["patient_id", "months_observed", "outcome"])
        for i in range(n):
            w.writerow(
                [
                    d["patient_id"][i],
                    d["months_observed"][i],
                    OUTCOME_LABEL[d["event"][i]],
                ]
            )

    seen = {}
    for i in range(n):
        seen[d["site_id"][i]] = d["cutoff"][i]
    with open(os.path.join(out_dir, "site_calendar.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["site_id", "administrative_cutoff_month"])
        for s in sorted(seen):
            w.writerow([s, int(seen[s])])

    return d


def load_cohort(data_dir):
    """Read the three-file bundle back into aligned numeric arrays (verifier side)."""
    cutoff = {}
    with open(os.path.join(data_dir, "site_calendar.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            cutoff[int(row["site_id"])] = float(row["administrative_cutoff_month"])

    enroll = {}
    with open(os.path.join(data_dir, "enrollment.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            enroll[row["patient_id"]] = {
                "site": int(row["site_id"]),
                "enroll_month": float(row["enroll_month"]),
                "therapy": LABEL_THERAPY[row["therapy"].strip()],
                "F": int(row["stage_high"]),
                "G": int(row["marker_high"]),
                "C": float(row["baseline_index"]),
            }

    A, F, G, C, months, event, cens_admin = [], [], [], [], [], [], []
    with open(os.path.join(data_dir, "followup.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            pid = row["patient_id"]
            rec = enroll[pid]
            A.append(rec["therapy"])
            F.append(rec["F"])
            G.append(rec["G"])
            C.append(rec["C"])
            months.append(float(row["months_observed"]))
            event.append(LABEL_OUTCOME[row["outcome"].strip()])
            cens_admin.append(cutoff[rec["site"]] - rec["enroll_month"])
    return {
        "A": np.array(A),
        "F": np.array(F),
        "G": np.array(G),
        "C": np.array(C),
        "months": np.array(months),
        "event": np.array(event),
        "cens_admin": np.array(cens_admin),
    }
