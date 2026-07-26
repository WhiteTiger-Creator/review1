"""Independent semantic lineage model for the lineage-audit policy.

This module deliberately does NOT import, call, or read the Java implementation.
It encodes the same governance policy described in the model-review dossier so
that the verifier can compute expected canonical graphs, feature paths, AUC
deltas, and discrepancy classifications for arbitrary generated fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal

ANNOTATION_VOCAB = [
    "warmstart",
    "calibration_member",
    "ensemble_member",
    "feature_inheritance",
    "promotion",
    "quarantine",
]
STAGE_KINDS = ["train", "calibrate", "promote", "ensemble"]
RELEASE_STATUS = ["released", "candidate", "quarantined"]

QUANTUM = Decimal("0.000001")


class AuditError(Exception):
    """Raised for fatal, atomic-failure conditions.

    exit_code is the process exit code the Java tool must return; code is the
    stable diagnostic token that must appear on stderr.
    """

    def __init__(self, exit_code: int, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.exit_code = exit_code
        self.code = code
        self.message = message or code


@dataclass
class Run:
    uid: str
    release_alias: str
    legacy_alias: str
    stage: str
    release_status: str
    cohort: str
    feature_set_hash: str
    auc: str  # decimal string in the ledger


@dataclass
class Annotation:
    status: str  # proposal | approved | superseded
    date: str  # ISO YYYY-MM-DD
    content: str  # one of ANNOTATION_VOCAB


@dataclass
class Edge:
    parent: str
    child: str
    annotations: list[Annotation] = field(default_factory=list)


@dataclass
class Manifest:
    """Semantic ground truth for one lineage case.

    runs maps run_uid -> Run for every run referenced by the graph.  edges lists
    the logical parent->child relationships with their annotation candidates
    (the union of what both worktrees encode).
    """

    runs: dict[str, Run]
    edges: list[Edge]


# --------------------------------------------------------------------------
# Annotation precedence
# --------------------------------------------------------------------------


def canonical_annotation(annotations: list[Annotation]) -> str:
    """Resolve the authoritative annotation content for an edge.

    Rules (from the dossier): superseded candidates are ignored; an approved
    decision outranks a proposal; among equal status the later decision date
    wins; ties break on content lexical order.
    """
    live = [a for a in annotations if a.status != "superseded"]
    if not live:
        return "unspecified"

    def rank(a: Annotation) -> tuple:
        status_rank = 0 if a.status == "approved" else 1
        # later date should sort first -> invert by using negative ordinal via
        # descending compare implemented with a reversed string is fragile, so
        # sort ascending and pick last for date; keep status primary.
        return (status_rank, a.date, a.content)

    # Highest precedence = approved (status_rank 0) with the latest date.
    live.sort(key=lambda a: (0 if a.status == "approved" else 1,))
    best_status = 0 if any(a.status == "approved" for a in live) else 1
    same = [a for a in live if (0 if a.status == "approved" else 1) == best_status]
    same.sort(key=lambda a: (a.date, a.content))
    return same[-1].content


# --------------------------------------------------------------------------
# Feature-path construction
# --------------------------------------------------------------------------


def _parents_map(edges: list[Edge]) -> dict[str, list[str]]:
    parents: dict[str, list[str]] = {}
    for e in edges:
        parents.setdefault(e.child, [])
        parents[e.child].append(e.parent)
        parents.setdefault(e.parent, parents.get(e.parent, []))
    for k, vals in parents.items():
        parents[k] = sorted(vals)
    return parents


def _feature_changing(uid: str, parents: list[str], runs: dict[str, Run]) -> bool:
    stage = runs[uid].stage
    if not parents:
        return True
    if stage == "ensemble":
        return True
    if stage == "train":
        return any(
            runs[uid].feature_set_hash != runs[p].feature_set_hash for p in parents
        )
    # calibrate / promote never change the feature set
    return False


def feature_paths(manifest: Manifest) -> dict[str, str]:
    runs = manifest.runs
    parents = _parents_map(manifest.edges)
    memo: dict[str, str] = {}

    def path(uid: str) -> str:
        if uid in memo:
            return memo[uid]
        ps = parents.get(uid, [])
        if not ps:
            result = uid
        elif len(ps) == 1:
            p = ps[0]
            if _feature_changing(uid, ps, runs):
                result = path(p) + ">" + uid
            else:
                result = path(p)
        else:
            base = "[" + "|".join(sorted(path(p) for p in ps)) + "]"
            # ensemble stage is always feature-changing
            result = base + ">" + uid
        memo[uid] = result
        return result

    return {uid: path(uid) for uid in runs}


# --------------------------------------------------------------------------
# AUC delta / baseline selection
# --------------------------------------------------------------------------


def _nearest_released_baseline(
    child: str, start_parent: str, manifest: Manifest
) -> str | None:
    runs = manifest.runs
    parents = _parents_map(manifest.edges)
    cohort = runs[child].cohort
    # BFS upward starting from the edge's parent (distance 1).
    frontier = [start_parent]
    seen = set()
    while frontier:
        frontier.sort()
        next_frontier: list[str] = []
        for nid in frontier:
            if nid in seen:
                continue
            seen.add(nid)
            r = runs.get(nid)
            if r is None:
                continue
            if r.release_status == "released" and r.cohort == cohort:
                return nid
            for p in parents.get(nid, []):
                if p not in seen:
                    next_frontier.append(p)
        frontier = next_frontier
    return None


def auc_delta(child: str, baseline: str, manifest: Manifest) -> str:
    runs = manifest.runs
    delta = (Decimal(runs[child].auc) - Decimal(runs[baseline].auc)).quantize(
        QUANTUM, rounding=ROUND_HALF_EVEN
    )
    return f"{delta:.6f}"


# --------------------------------------------------------------------------
# Full canonical reconciliation
# --------------------------------------------------------------------------


def reconcile(manifest: Manifest) -> dict:
    """Return the expected canonical graph for a valid manifest.

    Raises AuditError for fatal conditions the caller wants to assert on.
    """
    runs = manifest.runs
    # Unknown-run check: every edge endpoint must exist in the ledger.
    for e in manifest.edges:
        if e.parent not in runs:
            raise AuditError(2, "UNKNOWN_RUN", f"unknown run {e.parent}")
        if e.child not in runs:
            raise AuditError(2, "UNKNOWN_RUN", f"unknown run {e.child}")

    paths = feature_paths(manifest)

    nodes = [{"run_uid": uid, "feature_path": paths[uid]} for uid in sorted(runs)]

    edges_out = []
    for e in sorted(manifest.edges, key=lambda x: (x.parent, x.child)):
        annotation = canonical_annotation(e.annotations)
        baseline = _nearest_released_baseline(e.child, e.parent, manifest)
        entry = {"parent": e.parent, "child": e.child, "annotation": annotation}
        if baseline is not None:
            entry["baseline"] = baseline
            entry["auc_delta"] = auc_delta(e.child, baseline, manifest)
        edges_out.append(entry)

    return {
        "node_count": len(nodes),
        "edge_count": len(edges_out),
        "nodes": nodes,
        "edges": edges_out,
        "semantic_discrepancies": [],
    }
