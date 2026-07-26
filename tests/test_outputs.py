"""Verification for clicklog-propensity-ranker.

The agent's ranking pipeline (Go module under /app/rank) is rebuilt from source and
run here, so a hardcoded /app/output/ranker.json cannot pass. Grading uses a held-out
set of expert-judged queries rebuilt at grade time by heldout_refbuild.py, which never
appears in the agent environment: ranking quality (nDCG) on the canonical feature basis
plus recovery of the per-page-slot examination propensities. Config values below are
hardcoded (never read from /app/data).

Threshold calibration, measured on the shipped data. nDCG: oracle 0.999, slot-blind or
basis-blind fits 0.61 to 0.91, floor 0.95. Propensity L1: oracle 0.064 and at most 0.081
across optimizer settings, cheapest wrong recovery 0.371 for the correct basis on the
logged rank index and 0.294 for a slot fix without the basis fix, tolerance 0.16. Weight
cosine: oracle 0.998, naive click fit 0.214, slot-only fit -0.103, floor 0.90.

The scores the model file drives are within-query orderings and a scale-free propensity
curve, so no graded quantity depends on an additive score offset; the model file carries
no intercept and none is read here.
"""

import functools
import json
import math
import operator
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import heldout_refbuild

RANK_DIR = Path("/app/rank")
OUT = Path("/app/output/ranker.json")

NUM_FEATURES = 12
NUM_SLOTS = 10


@functools.cache
def _heldout():
    return heldout_refbuild.build_heldout()


THETA_TRUE = [
    1.0,
    0.450625,
    0.28269,
    0.203063,
    0.157103,
    0.127387,
    0.106693,
    0.091505,
    0.079914,
    0.070795,
]

W_TRUE = [
    0.771068,
    0.986082,
    -0.12868,
    0.358763,
    -0.108966,
    -0.600956,
    0.4452,
    0.260751,
    0.050188,
    0.196566,
    0.236128,
    0.334209,
]

NDCG_THRESHOLD = 0.95
PROP_L1_TOL = 0.16
RAW_CLICK_NDCG = 0.910
BEATS_MARGIN = 0.02
WEIGHT_COS_MIN = 0.90


@pytest.fixture(scope="module", autouse=True)
def build_and_run():
    build = subprocess.run(
        ["go", "build", "-o", "/app/rank/rankbin", "."],
        cwd=str(RANK_DIR),
        capture_output=True,
        text=True,
        timeout=420,
        check=False,
    )
    assert build.returncode == 0, f"go build failed:\n{build.stderr}"
    if OUT.exists():
        OUT.unlink()
    run = subprocess.run(
        ["/app/rank/rankbin"],
        cwd=str(RANK_DIR),
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert run.returncode == 0, f"ranker run failed:\n{run.stderr}"


def _load_ranker():
    """Read the model file the rebuilt pipeline just wrote."""
    assert OUT.exists(), "ranker.json was not produced by the rebuilt pipeline"
    return json.loads(OUT.read_text())


def _dcg(grades, k):
    """Discounted cumulative gain of a graded ordering over its first k entries."""
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades[:k]))


def _mean_ndcg(ranker):
    """Mean nDCG of the model's ordering across the held-out judged queries."""
    w = ranker["relevance_weights"]
    k = heldout_refbuild.CUTOFF

    def score(feat):
        return sum(wi * xi for wi, xi in zip(w, feat, strict=True))

    vals = []
    for q in _heldout():
        docs = q["docs"]
        ranked = sorted(docs, key=lambda d: score(d["features"]), reverse=True)
        ideal = sorted(docs, key=operator.itemgetter("grade"), reverse=True)
        idcg = _dcg([d["grade"] for d in ideal], k)
        if idcg <= 0:
            continue
        vals.append(_dcg([d["grade"] for d in ranked], k) / idcg)
    return sum(vals) / len(vals)


def _norm_theta(theta):
    t0 = theta[0]
    if t0 == 0:
        return theta
    return [t / t0 for t in theta]


def test_ranker_artifact_built():
    """The rebuilt pipeline emits a ranker.json carrying both required fields."""
    r = _load_ranker()
    assert "slot_propensities" in r
    assert "relevance_weights" in r


def test_ranker_wellformed():
    """Propensities and weights are the right shape, finite, and in range."""
    r = _load_ranker()
    theta = r["slot_propensities"]
    w = r["relevance_weights"]
    assert len(theta) == NUM_SLOTS, (
        f"expected {NUM_SLOTS} propensities, got {len(theta)}"
    )
    assert len(w) == NUM_FEATURES, f"expected {NUM_FEATURES} weights, got {len(w)}"
    for t in theta:
        assert math.isfinite(t) and 0.0 < t <= 1.0001, f"propensity out of range: {t}"
    for wi in w:
        assert math.isfinite(wi), "non-finite weight"


def test_heldout_ndcg_above_threshold():
    """The relevance weights rank the held-out judged queries above the quality floor.

    The judged features are on the canonical basis, so a fit that ignores how the shipped
    feature columns are scaled scores well below this floor even when its ordering of the
    logged data looks good.
    """
    r = _load_ranker()
    ndcg = _mean_ndcg(r)
    assert ndcg >= NDCG_THRESHOLD, (
        f"held-out nDCG {ndcg:.4f} below threshold {NDCG_THRESHOLD}"
    )


def test_ndcg_beats_naive_click_baseline():
    """The model generalizes strictly better than a ranker fit to the raw clicks."""
    r = _load_ranker()
    ndcg = _mean_ndcg(r)
    assert ndcg >= RAW_CLICK_NDCG + BEATS_MARGIN, (
        f"held-out nDCG {ndcg:.4f} does not beat the raw-click baseline "
        f"{RAW_CLICK_NDCG} by {BEATS_MARGIN}"
    )


def test_slot_propensities_recovered():
    """Recovered examination propensities match the true per-page-slot curve.

    The curve is compared after normalizing by its own first entry, so any positive
    scaling is accepted. An estimate indexed by the logged retrieval rank rather than the
    rendered page slot lands at more than twice this tolerance.
    """
    r = _load_ranker()
    theta = _norm_theta(r["slot_propensities"])
    l1 = sum(abs(a - b) for a, b in zip(theta, THETA_TRUE, strict=True))
    assert l1 <= PROP_L1_TOL, (
        f"recovered examination propensities L1 error {l1:.4f} exceeds tolerance "
        f"{PROP_L1_TOL} (an estimate indexed by anything other than the rendered page "
        f"slot does not pass)"
    )


def test_slot_propensities_not_uniform():
    """A degenerate near-uniform examination curve is rejected."""
    r = _load_ranker()
    theta = _norm_theta(r["slot_propensities"])
    spread = max(theta) - min(theta)
    assert spread >= 0.3, (
        f"examination propensities are near-uniform (spread {spread:.3f}); not recovered"
    )


def test_relevance_weights_aligned():
    """The debiased weights point along the true relevance direction on the canonical basis."""
    r = _load_ranker()
    w = r["relevance_weights"]
    dot = sum(a * b for a, b in zip(w, W_TRUE, strict=True))
    nw = math.sqrt(sum(a * a for a in w))
    nt = math.sqrt(sum(b * b for b in W_TRUE))
    assert nw > 0, "zero relevance weights"
    cos = dot / (nw * nt)
    assert cos >= WEIGHT_COS_MIN, (
        f"relevance weights align {cos:.4f} with the true relevance direction, "
        f"below {WEIGHT_COS_MIN} (a model fit to the shipped feature values as they "
        f"stand aligns far lower)"
    )
