"""Verify-time reference rebuild for clicklog-propensity-ranker.

The held-out expert-judged evaluation set is NOT shipped. The verifier rebuilds it here
at grade time on the canonical feature basis from the system's true relevance direction
and a fixed held-out seed, so the graded queries never appear in the agent image. Values
below are the hidden ground truth and are hardcoded (rule 3).
"""

import math
import random

CUTOFF = 10
NUM_FEATURES = 12
N_HELDOUT = 1400
C_HELDOUT = 12
HELDOUT_SEED = 88017701

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
B_TRUE = -0.15

GRADE_CUTS = [0.15, 0.35, 0.55, 0.75]


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _grade(r):
    for g, cut in enumerate(GRADE_CUTS):
        if r < cut:
            return g
    return 4


def build_heldout():
    rng = random.Random(HELDOUT_SEED)
    queries = []
    for q in range(N_HELDOUT):
        docs = []
        for _ in range(C_HELDOUT):
            x = [rng.gauss(0.0, 1.0) for _ in range(NUM_FEATURES)]
            z = B_TRUE + sum(w * xi for w, xi in zip(W_TRUE, x))
            docs.append({"features": x, "grade": _grade(_sigmoid(z))})
        queries.append({"query_id": 100000 + q, "docs": docs})
    return queries
