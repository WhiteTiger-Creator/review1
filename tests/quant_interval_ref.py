"""Verifier-only interval math helpers for qbound certification tests.

This module is not part of the agent environment image. Tests compare the
compiled qbound-analyzer binary against this independent recomputation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

BIN = Path("/app/build/qbound-analyzer")
OUTPUT = Path("/app/output/drift_certification_report.json")
GRAPH_ROOT = Path("/app/fixtures/static-graphs")
VARIANT_ROOT = Path("/app/fixtures/quant-variants")
SCENARIO_ROOT = Path("/app/fixtures/drift-scenarios")
STAGING = Path("/app/var/qbound-interval-store")
STAGING_ROOT = STAGING
POISON_ROOT = Path("/opt/verifier-fixtures/tb3/poison-pack")


def invoke(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(BIN), *args], capture_output=True, text=True, check=False)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def affine_ref(iv: tuple[float, float], w: float, b: float) -> tuple[float, float]:
    lo, hi = iv
    if w >= 0:
        return w * lo + b, w * hi + b
    return w * hi + b, w * lo + b


def affine_quant(iv: tuple[float, float], wt: dict) -> tuple[float, float]:
    scale = float(wt["scale"])
    zp = int(wt["zero_point"])
    w_d = (int(wt["w_q"]) - zp) * scale
    b_d = (int(wt["b_q"]) - zp) * scale
    err = scale
    mid = affine_ref(iv, w_d, b_d)
    return mid[0] - err, mid[1] + err


def relu(iv: tuple[float, float]) -> tuple[float, float]:
    lo, hi = iv
    lo2 = max(0.0, lo)
    hi2 = hi if lo < 0.0 < hi else max(0.0, hi)
    return lo2, hi2


def round6(value: float) -> float:
    """Match layer-intervals.json %.6f persistence in bound-workspace-snapshot.md."""
    return round(value, 6)


def drift(ref: tuple[float, float], quant: tuple[float, float]) -> float:
    return max(abs(ref[0] - quant[0]), abs(ref[1] - quant[1]))


def topo_layers(graph: dict) -> list[dict]:
    layers = graph["layers"]
    by_id = {layer["id"]: layer for layer in layers}
    order: list[dict] = []
    seen: set[str] = set()

    def visit(lid: str) -> None:
        if lid in seen:
            return
        layer = by_id[lid]
        for inp in layer.get("inputs", []):
            visit(inp)
        seen.add(lid)
        order.append(layer)

    for layer in layers:
        visit(layer["id"])
    return order


def merge_variant(weights: dict, variant: dict) -> dict:
    merged = {k: dict(v) for k, v in weights.items()}
    for key, override in variant.get("overrides", {}).items():
        merged[key] = {**merged[key], **override}
    return merged


def propagate_graph(
    graph: dict,
    weights: dict,
    variant: dict,
    scenario: dict,
) -> tuple[list[dict], float, int]:
    weights = merge_variant(weights, variant)
    epoch = int(graph.get("certification_epoch", 0))
    input_iv = (
        float(scenario["input_interval"]["lo"]),
        float(scenario["input_interval"]["hi"]),
    )
    bound = float(scenario["drift_bound"])
    rows: list[dict] = []
    state_ref: dict[str, tuple[float, float]] = {}
    state_quant: dict[str, tuple[float, float]] = {}
    for layer in topo_layers(graph):
        lid = layer["id"]
        op = layer["op"]
        if op == "input":
            ref_iv = input_iv
            quant_iv = input_iv
        else:
            src = layer["inputs"][0]
            ref_iv = state_ref[src]
            quant_iv = state_quant[src]
        if op == "affine":
            wkey = layer["weight_key"]
            wt = weights[wkey]
            ref_iv = affine_ref(ref_iv, float(wt["w"]), float(wt["b"]))
            quant_iv = affine_quant(quant_iv, wt)
        elif op == "relu":
            ref_iv = relu(ref_iv)
            quant_iv = relu(quant_iv)
        ref_iv = (round6(ref_iv[0]), round6(ref_iv[1]))
        quant_iv = (round6(quant_iv[0]), round6(quant_iv[1]))
        state_ref[lid] = ref_iv
        state_quant[lid] = quant_iv
        layer_drift = drift(ref_iv, quant_iv)
        rows.append(
            {
                "layer_id": lid,
                "ref": {"lo": ref_iv[0], "hi": ref_iv[1]},
                "quant": {"lo": quant_iv[0], "hi": quant_iv[1]},
                "drift": layer_drift,
            }
        )
    return rows, bound, epoch


def pack_paths(
    graph_id: str,
    variant_id: str,
    scenario_id: str,
    graph_root: Path | None,
    variant_root: Path | None,
    scenario_root: Path | None,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    gr = graph_root or GRAPH_ROOT
    vr = variant_root or VARIANT_ROOT
    sr = scenario_root or SCENARIO_ROOT
    return (
        gr,
        gr / graph_id,
        vr,
        vr / variant_id / "variant.json",
        sr,
        sr / scenario_id / "scenario.json",
    )


def independent_violations(
    graph_id: str,
    variant_id: str,
    scenario_id: str,
    graph_root: Path | None = None,
    variant_root: Path | None = None,
    scenario_root: Path | None = None,
) -> list[dict]:
    _, graph_dir, _, variant_path, _, scenario_path = pack_paths(
        graph_id, variant_id, scenario_id, graph_root, variant_root, scenario_root
    )
    graph = load_json(graph_dir / "graph.json")
    weights = load_json(graph_dir / "weights.json")
    variant = load_json(variant_path)
    scenario = load_json(scenario_path)
    rows, bound, epoch = propagate_graph(graph, weights, variant, scenario)
    violations = []
    for row in rows:
        d = row["drift"]
        bad = d >= bound if epoch == 2 else d > bound
        if bad:
            violations.append(
                {"layer_id": row["layer_id"], "measured_drift": d, "bound": bound}
            )
    violations.sort(key=lambda v: v["layer_id"])
    return violations


def contract_digest(graph_id: str, variant_id: str, scenario_id: str, violations: list[dict]) -> str:
    """SHA256 digest per /app/docs/drift-report-contract.md digest_input rules."""
    buf = f"{graph_id}{variant_id}{scenario_id}"
    for v in violations:
        buf += f"{v['layer_id']}{v['measured_drift']:.6f}"
    return hashlib.sha256(buf.encode()).hexdigest()


def walk_witness_digest(snap: dict) -> str:
    """SHA256 of layer_id concatenation in topological snap order per walk-witness-contract.md."""
    buf = "".join(row["layer_id"] for row in snap["layers"])
    return hashlib.sha256(buf.encode()).hexdigest()


def read_walk_witness(staging_dir: Path) -> str:
    data = load_json(staging_dir / "walk-witness.json")
    return str(data["layer_order_digest"])


def read_publish_seq(graph_id: str) -> int:
    ledger = Path("/app/var/qbound-cert-ledger/publish-seq.json")
    if not ledger.is_file():
        return 0
    data = load_json(ledger)
    if data.get("graph_id") != graph_id:
        return 0
    return int(data.get("publish_seq", 0))


def run_pipeline(
    graph_id: str,
    variant_id: str,
    scenario_id: str,
    graph_root: str | None = None,
    variant_root: str | None = None,
    scenario_root: str | None = None,
) -> None:
    gr = graph_root or str(GRAPH_ROOT)
    vr = variant_root or str(VARIANT_ROOT)
    sr = scenario_root or str(SCENARIO_ROOT)
    invoke(
        [
            "ingest-pack",
            "--graph-root",
            gr,
            "--graph",
            graph_id,
            "--variant-root",
            vr,
            "--variant",
            variant_id,
            "--scenario-root",
            sr,
            "--scenario",
            scenario_id,
        ]
    )
    invoke(["walk-intervals", "--graph", graph_id])
    invoke(["publish-report", "--graph", graph_id])


def load_report() -> dict:
    return load_json(OUTPUT)


reference_walk = independent_violations
