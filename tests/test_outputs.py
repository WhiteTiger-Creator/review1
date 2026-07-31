"""INT8 model compression certification — feature interval propagation verifier."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from quant_interval_ref import (
    BIN,
    POISON_ROOT,
    STAGING,
    independent_violations,
    invoke,
    load_report,
    read_publish_seq,
    read_walk_witness,
    reference_walk,
    run_pipeline,
    walk_witness_digest,
)

_PROBE_REFERENCE = reference_walk


def _read_snap(graph_id: str) -> dict:
    return json.loads((STAGING / graph_id / "layer-intervals.json").read_text(encoding="utf-8"))


def _pick_layer(snap: dict, layer_id: str) -> dict:
    return next(row for row in snap["layers"] if row["layer_id"] == layer_id)


def test_qboundcert_compilegate_analyzer_smoke_rc0():
    """Verifies rebuild-qbound-analyzer.sh leaves the qbound-analyzer binary at /app/build."""
    assert BIN.is_file()
    proc = subprocess.run([str(BIN), "smoke-publish"], capture_output=True, text=True, check=False)
    assert proc.returncode == 0


def test_qboundcert_loadpack_stderrbanner_clean_qbound_ingest_ok():
    """Verifies ingest-pack succeeds and prints QBOUND_INGEST_OK per qdrift-cli-surface.md."""
    proc = invoke(
        [
            "ingest-pack",
            "--graph-root",
            "/app/fixtures/static-graphs",
            "--graph",
            "linear-clean",
            "--variant-root",
            "/app/fixtures/quant-variants",
            "--variant",
            "v-int8-tight",
            "--scenario-root",
            "/app/fixtures/drift-scenarios",
            "--scenario",
            "scenario-tight",
        ]
    )
    assert proc.returncode == 0
    assert "QBOUND_INGEST_OK" in proc.stderr


def test_qboundcert_staging_context_graph_variant_scenario():
    """Verifies pack-context.json records graph, variant, and scenario ids after ingest-pack."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    pack_context = json.loads((STAGING / "linear-clean" / "pack-context.json").read_text(encoding="utf-8"))
    assert pack_context["graph_id"] == "linear-clean"
    assert pack_context["variant_id"] == "v-int8-tight"
    assert pack_context["scenario_id"] == "scenario-tight"


def test_qboundcert_walkpass_stderrbanner_hetero_qbound_walk_ok():
    """Verifies walk-intervals succeeds and prints QBOUND_WALK_OK for linear-mixed."""
    invoke(
        [
            "ingest-pack",
            "--graph-root",
            "/app/fixtures/static-graphs",
            "--graph",
            "linear-mixed",
            "--variant-root",
            "/app/fixtures/quant-variants",
            "--variant",
            "v-int8-loose",
            "--scenario-root",
            "/app/fixtures/drift-scenarios",
            "--scenario",
            "scenario-standard",
        ]
    )
    proc = invoke(["walk-intervals", "--graph", "linear-mixed"])
    assert proc.returncode == 0
    assert "QBOUND_WALK_OK" in proc.stderr


def test_qboundcert_topo_layer_sequence_in_snap():
    """Verifies layer-intervals.json lists layers in topological dependency order."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    snap = _read_snap("linear-clean")
    assert [row["layer_id"] for row in snap["layers"]] == [
        "input",
        "aff1",
        "relu1",
        "aff2",
        "output",
    ]


def test_qboundcert_tight_linear_sealed_zero_overruns():
    """Verifies certified model export has zero eval drift metric violations on tight INT8 inference pack."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    ledger = load_report()
    assert ledger["certified"] is True
    assert ledger["violations"] == []
    assert ledger["graph_id"] == "linear-clean"


def test_qboundcert_hetero_overrun_layers_align_refmath():
    """Verifies violation layer ids match independent feature interval walk eval reference."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    ledger = load_report()
    ref_layers = sorted(
        v["layer_id"] for v in independent_violations("linear-mixed", "v-int8-loose", "scenario-standard")
    )
    got_layers = sorted(v["layer_id"] for v in ledger["violations"])
    assert got_layers == ref_layers


def test_qboundcert_overrun_drift_aligns_fp32_walk():
    """Verifies each violation measured_drift eval metric matches independent feature propagation math."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    ledger = load_report()
    ref_map = {
        v["layer_id"]: v
        for v in independent_violations("linear-mixed", "v-int8-loose", "scenario-standard")
    }
    for row in ledger["violations"]:
        expect = ref_map[row["layer_id"]]["measured_drift"]
        assert abs(row["measured_drift"] - expect) < 1e-5


def test_qboundcert_overrun_bounds_align_scenario_ceiling():
    """Verifies each violation row bound equals report drift_bound from scenario pack."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    ledger = load_report()
    for row in ledger["violations"]:
        assert abs(row["bound"] - ledger["drift_bound"]) < 1e-9


def test_qboundcert_sha256seal_aligns_fp32_walk():
    """Verifies model export digest matches drift-report-contract schema sha256 composition."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    ledger = load_report()
    ref_v = independent_violations("linear-mixed", "v-int8-loose", "scenario-standard")
    seal_src = (
        f"{ledger['graph_id']}{ledger['variant_id']}{ledger['scenario_id']}"
        + "".join(f"{v['layer_id']}{v['measured_drift']:.6f}" for v in ref_v)
    )
    assert ledger["digest"] == hashlib.sha256(seal_src.encode()).hexdigest()


def test_qboundcert_emit_stderrbanner_qbound_publish_ok():
    """Verifies publish-report export stage prints QBOUND_PUBLISH_OK on success."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    proc = invoke(["publish-report", "--graph", "linear-clean"])
    assert proc.returncode == 0
    assert "QBOUND_PUBLISH_OK" in proc.stderr


def test_qboundcert_aff1_envelope_under_tight_ceiling():
    """Verifies aff1 drift stays below tight scenario ceiling on linear-clean."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    aff1 = _pick_layer(_read_snap("linear-clean"), "aff1")
    assert aff1["drift"] < 0.02


def test_qboundcert_aff2_overrun_exceeds_standard_ceiling():
    """Verifies aff2 measured_drift exceeds scenario bound on linear-mixed loose variant."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    aff2_v = next(v for v in load_report()["violations"] if v["layer_id"] == "aff2")
    assert aff2_v["measured_drift"] > aff2_v["bound"]


def test_qboundcert_relu_quant_lows_nonnegative():
    """Verifies relu1 ref and quant interval lows are nonnegative after interval walk."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    relu_row = _pick_layer(_read_snap("linear-mixed"), "relu1")
    assert relu_row["ref"]["lo"] >= 0.0
    assert relu_row["quant"]["lo"] >= 0.0


def test_qboundcert_smoke_publish_subcmd_rc_zero():
    """Verifies smoke-publish subcommand exits zero for bundled regression path."""
    proc = invoke(["smoke-publish"])
    assert proc.returncode == 0


def test_qboundcert_terminal_snap_drift_equals_overrun_row():
    """Verifies output layer snapshot drift equals violation row measured_drift."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    terminal_snap = _pick_layer(_read_snap("linear-mixed"), "output")
    terminal_v = next(v for v in load_report()["violations"] if v["layer_id"] == "output")
    assert abs(terminal_snap["drift"] - terminal_v["measured_drift"]) < 1e-5


def test_qboundcert_hetero_unsealed_when_overruns_present():
    """Verifies certified false when linear-mixed loose variant has bound overruns."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    ledger = load_report()
    assert ledger["certified"] is False
    assert len(ledger["violations"]) >= 2


def test_qboundcert_ledger_variant_field_from_loadpack():
    """Verifies drift_certification_report.json inference variant_id schema field from ingest pack."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    assert load_report()["variant_id"] == "v-int8-tight"


def test_qboundcert_negweight_affine_ref_lo_le_hi():
    """Verifies aff2 float interval lo does not exceed hi with negative weights."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    aff2 = _pick_layer(_read_snap("linear-mixed"), "aff2")
    assert aff2["ref"]["lo"] <= aff2["ref"]["hi"]


def test_qboundcert_ledger_scenario_fields_from_pack():
    """Verifies report scenario_id and drift_bound match scenario-standard pack."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    ledger = load_report()
    assert ledger["scenario_id"] == "scenario-standard"
    assert abs(ledger["drift_bound"] - 0.08) < 1e-9


def test_qboundcert_hetero_overruns_include_aff2_terminal():
    """Verifies linear-mixed loose violations include aff2 and output per instruction."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    layers = {v["layer_id"] for v in load_report()["violations"]}
    assert {"aff2", "output"}.issubset(layers)


POISON = POISON_ROOT


def _run_poison_pipeline() -> None:
    invoke(
        [
            "ingest-pack",
            "--graph-root",
            str(POISON),
            "--graph",
            "linear-poison",
            "--variant-root",
            str(POISON),
            "--variant",
            "v-poison-int8",
            "--scenario-root",
            str(POISON),
            "--scenario",
            "scenario-tight",
        ]
    )
    invoke(["walk-intervals", "--graph", "linear-poison"])
    invoke(["publish-report", "--graph", "linear-poison"])


def test_qboundcert_tb3hidden_loadpack_from_opt_fixtures():
    """Verifies TB3 poison-pack ingest-pack succeeds from /opt/verifier-fixtures/tb3/poison-pack."""
    proc = invoke(
        [
            "ingest-pack",
            "--graph-root",
            str(POISON),
            "--graph",
            "linear-poison",
            "--variant-root",
            str(POISON),
            "--variant",
            "v-poison-int8",
            "--scenario-root",
            str(POISON),
            "--scenario",
            "scenario-tight",
        ]
    )
    assert proc.returncode == 0


def test_qboundcert_gatepass_two_strict_overruns_tb3hidden():
    """Verifies epoch-two strict bound flags poison linear-poison violations per policy."""
    assert Path("/opt/verifier-fixtures/tb3/poison-pack") == POISON
    _run_poison_pipeline()
    ledger = load_report()
    ref = independent_violations(
        "linear-poison",
        "v-poison-int8",
        "scenario-tight",
        graph_root=POISON,
        variant_root=POISON,
        scenario_root=POISON,
    )
    assert len(ledger["violations"]) == len(ref)
    assert ledger["certified"] == (len(ref) == 0)


def test_qboundcert_walk_witness_matches_topo_snap_order():
    """Verifies walk-witness.json layer_order_digest matches topological snap order reference."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    snap = _read_snap("linear-clean")
    got = read_walk_witness(STAGING / "linear-clean")
    expect = walk_witness_digest(snap)
    assert got == expect


def test_qboundcert_publish_ledger_sequence_bumps_after_export():
    """Verifies publish-seq.json increments after successful publish-report."""
    run_pipeline("linear-clean", "v-int8-tight", "scenario-tight")
    before = read_publish_seq("linear-clean")
    invoke(["publish-report", "--graph", "linear-clean"])
    after = read_publish_seq("linear-clean")
    assert after == before + 1


def _run_hetero_poison_pipeline() -> None:
    invoke(
        [
            "ingest-pack",
            "--graph-root",
            str(POISON),
            "--graph",
            "hetero-poison",
            "--variant-root",
            str(POISON),
            "--variant",
            "v-hetero-poison",
            "--scenario-root",
            str(POISON),
            "--scenario",
            "scenario-tight",
        ]
    )
    invoke(["walk-intervals", "--graph", "hetero-poison"])
    invoke(["publish-report", "--graph", "hetero-poison"])


def test_qboundcert_tb3hidden_hetero_poison_custom_weight_key():
    """Verifies hetero-poison custom inference weight key loads and eval metric matches reference."""
    _run_hetero_poison_pipeline()
    ledger = load_report()
    ref = independent_violations(
        "hetero-poison",
        "v-hetero-poison",
        "scenario-tight",
        graph_root=POISON,
        variant_root=POISON,
        scenario_root=POISON,
    )
    got_layers = sorted(v["layer_id"] for v in ledger["violations"])
    ref_layers = sorted(v["layer_id"] for v in ref)
    assert got_layers == ref_layers
    assert ledger["certified"] == (len(ref) == 0)


def test_qboundcert_stale_witness_blocks_republish_without_rewalk():
    """Verifies publish-report refuses when walk-witness digest disagrees with snapshot order."""
    run_pipeline("linear-mixed", "v-int8-loose", "scenario-standard")
    staging = STAGING / "linear-mixed"
    witness_path = staging / "walk-witness.json"
    witness_path.write_text('{"layer_order_digest":"deadbeef"}\n', encoding="utf-8")
    proc = invoke(["publish-report", "--graph", "linear-mixed"])
    assert proc.returncode != 0
