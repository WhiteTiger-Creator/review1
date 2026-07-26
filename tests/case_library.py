"""Semantic case library shared by the shipped fixture and generated tests.

Every manifest here is expressed only in domain terms (runs + edges +
annotation candidates).  Representations are produced by fixture_factory and
expectations by lineage_model.
"""

from __future__ import annotations

import random

from lineage_model import Annotation, Edge, Manifest, Run

COHORTS = ["cohortA", "cohortB"]


def _ann(status: str, date: str, content: str) -> Annotation:
    return Annotation(status=status, date=date, content=content)


def build_shipped_manifest() -> Manifest:
    """The lineage graph materialized into the two shipped worktrees."""
    R = {}

    def run(uid, ra, la, stage, status, cohort, fsh, auc):
        R[uid] = Run(uid, ra, la, stage, status, cohort, fsh, auc)

    run("run-01", "RB-01", "LG-a1", "train", "released", "cohortA", "fs-a", "0.800000")
    run("run-02", "RB-02", "LG-a2", "train", "released", "cohortA", "fs-a", "0.805000")
    run("run-03", "RB-03", "LG-a3", "train", "candidate", "cohortA", "fs-b", "0.812345")
    run(
        "run-04",
        "RB-04",
        "LG-a4",
        "calibrate",
        "released",
        "cohortA",
        "fs-b",
        "0.815000",
    )
    run(
        "run-05", "RB-05", "LG-a5", "promote", "released", "cohortA", "fs-b", "0.815000"
    )
    run("run-06", "RB-06", "LG-b1", "train", "released", "cohortB", "fs-c", "0.700000")
    run("run-07", "RB-07", "LG-b2", "train", "candidate", "cohortB", "fs-d", "0.734500")
    run(
        "run-08",
        "RB-08",
        "LG-b3",
        "calibrate",
        "released",
        "cohortB",
        "fs-d",
        "0.740000",
    )
    run(
        "run-09",
        "RB-09",
        "LG-e1",
        "ensemble",
        "released",
        "cohortA",
        "fs-e",
        "0.860000",
    )
    run(
        "run-10", "RB-10", "LG-e2", "promote", "released", "cohortA", "fs-e", "0.861000"
    )
    run("run-11", "RB-11", "LG-q1", "train", "released", "cohortA", "fs-a", "0.802000")
    run("run-12", "RB-12", "LG-q2", "train", "candidate", "cohortA", "fs-g", "0.640000")

    edges = [
        Edge("run-01", "run-02", [_ann("approved", "2025-01-05", "warmstart")]),
        Edge(
            "run-02",
            "run-03",
            [
                _ann("proposal", "2024-01-10", "warmstart"),
                _ann("approved", "2025-02-01", "feature_inheritance"),
            ],
        ),
        Edge(
            "run-03", "run-04", [_ann("approved", "2025-03-01", "calibration_member")]
        ),
        Edge("run-04", "run-05", [_ann("approved", "2025-03-10", "promotion")]),
        Edge(
            "run-06", "run-07", [_ann("approved", "2025-02-14", "feature_inheritance")]
        ),
        Edge(
            "run-07", "run-08", [_ann("approved", "2025-03-02", "calibration_member")]
        ),
        Edge("run-05", "run-09", [_ann("approved", "2025-04-01", "ensemble_member")]),
        Edge("run-08", "run-09", [_ann("approved", "2025-04-01", "ensemble_member")]),
        Edge("run-09", "run-10", [_ann("approved", "2025-04-15", "promotion")]),
        Edge(
            "run-11",
            "run-12",
            [
                _ann("proposal", "2024-06-01", "ensemble_member"),
                _ann("approved", "2025-01-01", "quarantine"),
                _ann("superseded", "2025-04-01", "warmstart"),
            ],
        ),
    ]
    return Manifest(runs=R, edges=edges)


def random_valid_manifest(seed: int, *, weird_aliases: bool = False) -> Manifest:
    """Build a random but valid lineage DAG for anti-hardcoding tests."""
    rng = random.Random(seed)
    n = rng.randint(6, 9)
    runs: dict[str, Run] = {}
    order = [f"g{seed}-{i:02d}" for i in range(n)]
    fsh_pool = [f"h{seed}{c}" for c in "abcdef"]
    for i, uid in enumerate(order):
        if i == 0:
            stage = "train"
        else:
            stage = rng.choice(["train", "train", "calibrate", "promote"])
        cohort = rng.choice(COHORTS)
        status = rng.choice(["released", "released", "candidate", "quarantined"])
        fsh = rng.choice(fsh_pool)
        auc = f"{rng.uniform(0.5, 0.95):.6f}"
        if weird_aliases and i % 2 == 0:
            ra = f'rc blue "{uid}"'
            la = f"légacy\\{uid}"
        else:
            ra = f"R{seed}_{i}"
            la = f"L{seed}_{i}"
        runs[uid] = Run(uid, ra, la, stage, status, cohort, fsh, auc)

    edges: list[Edge] = []
    vocab = ["warmstart", "calibration_member", "feature_inheritance", "promotion"]
    for i in range(1, n):
        parent = order[rng.randint(0, i - 1)]
        child = order[i]
        anns = [
            _ann("approved", f"2025-0{rng.randint(1, 9)}-1{i % 9}", rng.choice(vocab))
        ]
        if rng.random() < 0.5:
            anns.insert(0, _ann("proposal", "2024-01-01", rng.choice(vocab)))
        edges.append(Edge(parent, child, anns))

    # Optionally add a two-parent ensemble node.
    if n >= 5 and rng.random() < 0.6:
        p1, p2 = rng.sample(order[:-1], 2)
        euid = f"g{seed}-ens"
        runs[euid] = Run(
            euid,
            f"R{seed}_ens",
            f"L{seed}_ens",
            "ensemble",
            rng.choice(["released", "candidate"]),
            rng.choice(COHORTS),
            f"h{seed}ens",
            f"{rng.uniform(0.6, 0.99):.6f}",
        )
        edges.append(
            Edge(p1, euid, [_ann("approved", "2025-05-01", "ensemble_member")])
        )
        edges.append(
            Edge(p2, euid, [_ann("approved", "2025-05-01", "ensemble_member")])
        )
    return Manifest(runs=runs, edges=edges)
