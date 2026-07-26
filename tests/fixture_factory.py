"""Deterministic fixture generator for the lineage-audit verifier.

Given a semantic Manifest it writes a training-runs ledger CSV and two Git-style
worktree directories that encode the SAME logical lineage with different
branch-local identifiers, alias spellings, legacy Graphviz attribute placement,
statement order, and quoting.  It also returns the expected representation
differences so the verifier can assert them against the tool output.

The factory never encodes the answer: it only re-expresses the manifest in two
representations.  All semantic expectations come from lineage_model.reconcile.
"""

from __future__ import annotations

import random
from pathlib import Path

from lineage_model import Annotation, Manifest, Run

LEDGER_HEADER = (
    "run_uid,release_alias,legacy_alias,parent_uids,stage_kind,"
    "release_status,evaluation_cohort,feature_set_hash,auc,model_card"
)


def dot_quote(s: str) -> str:
    out = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"' + out + '"'


def _annotation_text(a: Annotation) -> str:
    return f"{a.status}|{a.date}|{a.content}"


def write_ledger(path: Path, manifest: Manifest) -> None:
    parents: dict[str, list[str]] = {uid: [] for uid in manifest.runs}
    for e in manifest.edges:
        parents.setdefault(e.child, []).append(e.parent)
    lines = [LEDGER_HEADER]
    for uid in sorted(manifest.runs):
        r = manifest.runs[uid]
        pj = ";".join(sorted(parents.get(uid, [])))
        lines.append(
            ",".join(
                [
                    r.uid,
                    r.release_alias,
                    r.legacy_alias,
                    pj,
                    r.stage,
                    r.release_status,
                    r.cohort,
                    r.feature_set_hash,
                    r.auc,
                    f"cards/{r.uid}.md",
                ]
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _edge_statement(src_id: str, dst_id: str, attrs: list[tuple[str, str]]) -> str:
    attr_txt = ", ".join(f"{k}={dot_quote(v)}" for k, v in attrs)
    return f"  {dot_quote(src_id)} -> {dot_quote(dst_id)} [{attr_txt}];"


def _distribute(
    annotations: list[Annotation],
) -> tuple[list[Annotation], list[Annotation]]:
    """Split annotation candidates across the two worktrees.

    Both sides carry at least one; the union is the full candidate set.
    """
    if len(annotations) <= 1:
        return list(annotations), list(annotations)
    left = annotations[0::2]
    right = annotations[1::2]
    if not left:
        left = [annotations[0]]
    if not right:
        right = [annotations[-1]]
    return left, right


def _alias_for(run: Run, side: str) -> str:
    return run.release_alias if side == "left" else run.legacy_alias


def write_worktrees(base: Path, manifest: Manifest, seed: int) -> dict:
    rng = random.Random(seed)
    left_dir = base / "rc-blue"
    right_dir = base / "rc-green"
    (left_dir / "lineage").mkdir(parents=True, exist_ok=True)
    (right_dir / "lineage").mkdir(parents=True, exist_ok=True)

    runs = manifest.runs

    # --- left worktree: node ids = release_alias, annotations in `label` ---
    left_nodes = [
        f"  {dot_quote(runs[u].release_alias)} [kind={dot_quote(runs[u].stage)}];"
        for u in sorted(runs)
    ]
    left_edges = []
    right_carriers: dict[tuple[str, str], set[str]] = {}
    left_carriers: dict[tuple[str, str], set[str]] = {}
    for e in manifest.edges:
        left_anns, right_anns = _distribute(e.annotations)
        s = runs[e.parent].release_alias
        d = runs[e.child].release_alias
        for a in left_anns:
            left_edges.append(_edge_statement(s, d, [("label", _annotation_text(a))]))
            left_carriers.setdefault((e.parent, e.child), set()).add("label")

    left_body = "\n".join(left_nodes + left_edges)
    (left_dir / "lineage" / "graph.dot").write_text(
        "digraph rc_blue {\n  graph [rankdir=LR];\n" + left_body + "\n}\n",
        encoding="utf-8",
    )
    (left_dir / ".lineage-audit.properties").write_text(
        "annotation.legacy_attrs=accept\nalias.namespace=release\n", encoding="utf-8"
    )

    # --- right worktree: node ids = legacy_alias, annotations in xlabel/taillabel,
    #     shuffled order, wrapped in a subgraph ---
    right_nodes = [
        f"    {dot_quote(runs[u].legacy_alias)} [kind={dot_quote(runs[u].stage)}];"
        for u in sorted(runs)
    ]
    rng.shuffle(right_nodes)
    right_edges = []
    shuffled_edges = list(manifest.edges)
    rng.shuffle(shuffled_edges)
    for e in shuffled_edges:
        left_anns, right_anns = _distribute(e.annotations)
        s = runs[e.parent].legacy_alias
        d = runs[e.child].legacy_alias
        carriers = ["xlabel", "taillabel"]
        for i, a in enumerate(right_anns):
            carrier = carriers[i % len(carriers)]
            right_edges.append(_edge_statement(s, d, [(carrier, _annotation_text(a))]))
            right_carriers.setdefault((e.parent, e.child), set()).add(carrier)

    right_body = "\n".join(right_nodes + right_edges)
    (right_dir / "lineage" / "graph.dot").write_text(
        "digraph rc_green {\n  graph [rankdir=LR];\n  subgraph cluster_release {\n"
        + right_body
        + "\n  }\n}\n",
        encoding="utf-8",
    )
    (right_dir / ".lineage-audit.properties").write_text(
        "annotation.legacy_attrs=accept\nalias.namespace=legacy\n", encoding="utf-8"
    )

    write_ledger(base / "training-runs.csv", manifest)

    # --- expected representation differences ---
    diffs = []
    for uid in sorted(runs):
        ra = runs[uid].release_alias
        la = runs[uid].legacy_alias
        if ra != la:
            diffs.append(
                {"kind": "alias_spelling", "run_uid": uid, "aliases": sorted([ra, la])}
            )
    edge_keys = sorted({(e.parent, e.child) for e in manifest.edges})
    for parent, child in edge_keys:
        carriers = sorted(
            left_carriers.get((parent, child), set())
            | right_carriers.get((parent, child), set())
        )
        if len(carriers) > 1:
            diffs.append(
                {
                    "kind": "annotation_placement",
                    "edge": f"{parent}>{child}",
                    "attributes": carriers,
                }
            )
    diffs.sort(key=lambda d: (d["kind"], d.get("run_uid", ""), d.get("edge", "")))
    return {
        "left": str(left_dir),
        "right": str(right_dir),
        "ledger": str(base / "training-runs.csv"),
        "representation_differences": diffs,
    }
