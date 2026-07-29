"""Additional hard Maxwell/Nedelec verifier coverage (checkpoint I/O, meshes, residuals)."""

from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest
from helpers.canonical_basis import payloads_match_canonical_contract
from helpers.checkpoint_tools import (
    MAGIC,
    OFF_ACTIVE_DOFS,
    OFF_EDGE_IDENTITIES,
    OFF_EDGE_IDENTITY_COUNT,
    OFF_ITERATIONS,
    OFF_LINEAGE_DIGEST,
    OFF_MAGIC,
    OFF_REQUESTED_MODES,
    OFF_VERSION,
    expected_edge_identities,
    fnv1a64,
    parse_checkpoint,
    patch_field,
    patch_lineage_and_checksum,
    rewrite_with_updates,
    sentinel_unchanged,
    write_sentinel,
)
from helpers.mesh_factory import (
    boundary_face_not_on_tetra_mesh,
    combined_transform,
    deterministic_perm,
    duplicate_coordinate_mesh,
    near_degenerate_valid_cavity_mesh,
    permute_coordinate_axes,
    scale_uniform,
    skewed_parallelepiped_mesh,
    stretched_cavity_mesh,
    translate_mesh,
    two_cell_rectangular_cavity_mesh,
    unit_cube_mesh,
)
from helpers.mode_payload_checks import (
    check_m_orthonormal,
    compare_physics_payloads,
    first_significant_coeff_positive,
    rayleigh_quotient,
)
from helpers.operator_checks import compare_clustered_spectra
from helpers.reference_nedelec import (
    ALGEBRAIC_TOL,
    BOUNDARY_TOL,
    DIVERGENCE_TOL,
    build_reference_solution,
    mass_orthonormality_residual,
    recompute_algebraic_residuals,
    recompute_divergence_residuals,
)
from helpers.run_solver import load_modes, run_solver

REF_VAL_RTOL = 1e-5
REF_ANGLE_TOL = 0.05
ZERO_TOL = 1e-8


@pytest.fixture(scope="session", autouse=True)
def rebuild_solver() -> None:
    shutil.rmtree("/app/build", ignore_errors=True)
    subprocess.run(["/app/scripts/build.sh"], check=True)


def _assert_residuals(payload: dict) -> None:
    for mode in payload["modes"]:
        res = mode["residuals"]
        assert res["boundary_trace"] <= BOUNDARY_TOL
        assert res["divergence"] <= DIVERGENCE_TOL
        assert res["algebraic"] <= ALGEBRAIC_TOL


def _solve(mesh: Path, modes: int, output: Path, **kwargs) -> dict:
    proc = run_solver(mesh, modes, output, **kwargs)
    assert proc.returncode == 0, proc.stderr
    payload = load_modes(output)
    assert payload["computed_modes"] == modes
    _assert_residuals(payload)
    return payload


def _assert_failed_without_valid_modes(proc: subprocess.CompletedProcess[str], output: Path) -> None:
    assert proc.returncode != 0, proc.stdout
    if output.exists():
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload.get("computed_modes", 0) < 1


def _checkpoint(mesh: Path, tmp_path: Path, *, modes: int = 4, after: int = 3) -> Path:
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh, modes, tmp_path / "partial.json", checkpoint=ckpt, checkpoint_after=after)
    assert proc.returncode == 0, proc.stderr
    assert ckpt.exists() and ckpt.stat().st_size > 0
    return ckpt


def _compare_payload_to_reference(mesh: Path, modes: int, payload: dict) -> None:
    ref = build_reference_solution(mesh, max(modes, 6))
    vals_cand = np.array([m["eigenvalue"] for m in payload["modes"]], dtype=float)
    ref_vals = np.asarray(ref["eigenvalues"][:modes], dtype=float)
    assert np.allclose(vals_cand, ref_vals, rtol=REF_VAL_RTOL, atol=0.0)


def test_checkpoint_file_is_created_and_parseable_after_success(tmp_path: Path) -> None:
    """Successful checkpoint runs emit a version-3 file the verifier parser can consume."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    assert env.magic == MAGIC
    assert env.version == 3
    assert env.consumed_entire_file


def test_checkpoint_little_endian_envelope_fields_are_exact(tmp_path: Path) -> None:
    """Fixed header and variable section offsets match the public checkpoint envelope."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    assert env.offsets["magic"] == OFF_MAGIC
    assert env.offsets["version"] == OFF_VERSION
    assert env.offsets["requested_modes"] == OFF_REQUESTED_MODES
    assert env.offsets["iterations"] == OFF_ITERATIONS
    assert env.offsets["active_dofs"] == OFF_ACTIVE_DOFS
    assert env.offsets["lineage_digest"] == OFF_LINEAGE_DIGEST
    assert env.offsets["edge_identity_count"] == OFF_EDGE_IDENTITY_COUNT
    assert env.offsets["edge_identities"] == OFF_EDGE_IDENTITIES
    assert env.edge_identity_count == env.active_dofs
    assert env.ritz_value_count == len(env.ritz_values)
    assert env.ritz_vector_count == len(env.ritz_vectors)
    assert env.cache_tag_length == len(env.cache_tag)
    assert env.checksum_offset + 8 == len(env.raw)


def test_checkpoint_lineage_digest_matches_edge_identity_bytes(tmp_path: Path) -> None:
    """Field 6 lineage digest equals FNV-1a over the raw edge-identity float64 bytes."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    env = parse_checkpoint(_checkpoint(mesh, tmp_path))
    edge_bytes = struct.pack(f"<{len(env.edge_identities)}d", *env.edge_identities)
    assert env.lineage_digest == fnv1a64(edge_bytes)


def test_checkpoint_checksum_matches_fields_one_through_fourteen(tmp_path: Path) -> None:
    """Field 15 checksum equals FNV-1a over every byte before the checksum field."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    env = parse_checkpoint(_checkpoint(mesh, tmp_path))
    assert env.checksum == fnv1a64(env.raw[: env.checksum_offset])


def test_checkpoint_edge_identities_are_finite_unique_and_canonical(tmp_path: Path) -> None:
    """Stored edge identities match the exact checkpoint-format FNV encoding in coefficient order."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    env = parse_checkpoint(_checkpoint(mesh, tmp_path))
    assert len(env.edge_identities) == env.active_dofs
    assert all(math.isfinite(x) for x in env.edge_identities)
    assert len(set(env.edge_identities)) == len(env.edge_identities)
    expected = expected_edge_identities(mesh)
    assert env.edge_identities == expected


def test_checkpoint_ritz_values_are_positive_sorted_physical_modes(tmp_path: Path) -> None:
    """Stored Ritz values are finite, positive physical modes sorted ascending."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    env = parse_checkpoint(_checkpoint(mesh, tmp_path))
    scale = max(1.0, max(abs(v) for v in env.ritz_values))
    threshold = ZERO_TOL * scale
    assert all(v > threshold for v in env.ritz_values)
    assert env.ritz_values == sorted(env.ritz_values)


def test_checkpoint_ritz_vectors_are_finite_and_dimensionally_consistent(tmp_path: Path) -> None:
    """Every stored Ritz vector length equals active_dofs with finite coefficients."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    env = parse_checkpoint(_checkpoint(mesh, tmp_path))
    for vec in env.ritz_vectors:
        assert vec.length == env.active_dofs
        assert all(math.isfinite(c) for c in vec.coefficients)


def test_checkpoint_file_has_no_trailing_bytes(tmp_path: Path) -> None:
    """Appending bytes after the checksum makes resume fail without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    ckpt.write_bytes(ckpt.read_bytes() + b"TRAIL")
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_wrong_magic_atomically(tmp_path: Path) -> None:
    """Mutating EMCK to invalid magic rejects resume and preserves output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    patch_field(ckpt, OFF_MAGIC, b"XXXX", recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_negative_requested_modes_atomically(tmp_path: Path) -> None:
    """Negative requested_modes values are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    patch_field(ckpt, OFF_REQUESTED_MODES, struct.pack("<i", -1), recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_negative_iterations_atomically(tmp_path: Path) -> None:
    """Negative iteration counts are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    patch_field(ckpt, OFF_ITERATIONS, struct.pack("<i", -5), recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_zero_active_dofs_atomically(tmp_path: Path) -> None:
    """Zero active_dofs checkpoints are rejected before publishing modes."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    patch_field(ckpt, OFF_ACTIVE_DOFS, struct.pack("<i", 0), recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_edge_identity_count_mismatch_atomically(tmp_path: Path) -> None:
    """edge_identity_count must equal active_dofs or resume is rejected atomically."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    patch_field(ckpt, OFF_EDGE_IDENTITY_COUNT, struct.pack("<I", env.active_dofs + 1), recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_ritz_vector_length_mismatch_atomically(tmp_path: Path) -> None:
    """A Ritz vector whose length disagrees with active_dofs is rejected atomically."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    assert env.ritz_vectors
    vec = env.ritz_vectors[0]
    patch_field(ckpt, vec.offset, struct.pack("<I", env.active_dofs + 1), recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_mutated_lineage_digest_atomically(tmp_path: Path) -> None:
    """Flipping only the stored lineage digest rejects resume without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    patch_field(ckpt, OFF_LINEAGE_DIGEST, struct.pack("<Q", env.lineage_digest ^ 0xFF), recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_mutated_checksum_atomically(tmp_path: Path) -> None:
    """Flipping only the final checksum rejects resume without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    patch_field(ckpt, env.checksum_offset, struct.pack("<Q", env.checksum ^ 0xFF), recompute_checksum=False)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_duplicate_edge_identity_atomically(tmp_path: Path) -> None:
    """Duplicate edge identities are rejected even when checksum and lineage are recomputed."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    ids = list(env.edge_identities)
    ids[1] = ids[0]
    rewrite_with_updates(ckpt, edge_identities=ids)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_unsorted_edge_identities_atomically(tmp_path: Path) -> None:
    """Swapping two encoded identities breaks canonical coefficient order and is rejected."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    ids = list(env.edge_identities)
    ids[0], ids[1] = ids[1], ids[0]
    rewrite_with_updates(ckpt, edge_identities=ids)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_nan_edge_identity_atomically(tmp_path: Path) -> None:
    """NaN edge identities are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    patch_field(ckpt, OFF_EDGE_IDENTITIES, struct.pack("<d", float("nan")), recompute_checksum=True)
    patch_lineage_and_checksum(ckpt)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rejects_infinite_ritz_value_atomically(tmp_path: Path) -> None:
    """Infinite Ritz values are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path)
    env = parse_checkpoint(ckpt)
    patch_field(ckpt, env.ritz_values_offset, struct.pack("<d", float("inf")), recompute_checksum=True)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad = run_solver(mesh, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_write_failure_does_not_publish_successful_modes(tmp_path: Path) -> None:
    """Failed checkpoint writes must not emit a successful modes payload."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    out = tmp_path / "out.json"
    write_sentinel(out)
    bad_ckpt = tmp_path / "missing" / "state.bin"
    proc = run_solver(mesh, 4, out, checkpoint=bad_ckpt, checkpoint_after=2)
    _assert_failed_without_valid_modes(proc, out)
    assert sentinel_unchanged(out)


def test_missing_resume_checkpoint_preserves_existing_output(tmp_path: Path) -> None:
    """Missing resume checkpoints fail without modifying an existing output file."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    out = tmp_path / "out.json"
    write_sentinel(out)
    missing = tmp_path / "does_not_exist.bin"
    bad = run_solver(mesh, 4, out, resume=missing)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_from_axis_permuted_mesh_resumes_on_canonical_mesh(tmp_path: Path) -> None:
    """Axis-permuted checkpoints resume on an identically permuted mesh with matching clustered spectra."""
    base = unit_cube_mesh()
    perm = (2, 0, 1)
    mesh_a = tmp_path / "axes_a.mesh"
    mesh_b = tmp_path / "axes_b.mesh"
    permute_coordinate_axes(base, perm).write(mesh_a)
    permute_coordinate_axes(base, perm).write(mesh_b)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh_a, 4, tmp_path / "partial.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    direct = _solve(mesh_b, 4, tmp_path / "direct.json")
    resumed = _solve(mesh_b, 4, tmp_path / "resumed.json", resume=ckpt)
    assert compare_clustered_spectra(
        [m["eigenvalue"] for m in direct["modes"]],
        [m["coefficients"] for m in direct["modes"]],
        [m["eigenvalue"] for m in resumed["modes"]],
        [m["coefficients"] for m in resumed["modes"]],
        val_tol=REF_VAL_RTOL,
        angle_tol=REF_ANGLE_TOL,
    )
    incompatible = tmp_path / "stretched.mesh"
    stretched_cavity_mesh((1.25, 1.0, 1.0)).write(incompatible)
    out = tmp_path / "bad.json"
    write_sentinel(out)
    bad = run_solver(incompatible, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_from_translated_mesh_resumes_on_translated_copy_only(tmp_path: Path) -> None:
    """Translated checkpoints resume only on the same translated geometry."""
    base = unit_cube_mesh()
    offset = (12.0, -4.0, 2.5)
    mesh_a = tmp_path / "translated.mesh"
    mesh_b = tmp_path / "translated_copy.mesh"
    translate_mesh(base, offset).write(mesh_a)
    translate_mesh(base, offset).write(mesh_b)
    canonical = tmp_path / "canonical.mesh"
    base.write(canonical)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh_a, 4, tmp_path / "partial.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    resumed = _solve(mesh_b, 4, tmp_path / "resumed.json", resume=ckpt)
    assert resumed["computed_modes"] == 4
    out = tmp_path / "bad.json"
    write_sentinel(out)
    bad = run_solver(canonical, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_from_scaled_mesh_rejects_unscaled_mesh(tmp_path: Path) -> None:
    """Uniformly scaled checkpoints reject the unscaled geometry."""
    base = unit_cube_mesh()
    mesh_a = tmp_path / "scaled.mesh"
    mesh_b = tmp_path / "canonical.mesh"
    scale_uniform(base, 1.6).write(mesh_a)
    base.write(mesh_b)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh_a, 4, tmp_path / "partial.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    out = tmp_path / "bad.json"
    write_sentinel(out)
    bad = run_solver(mesh_b, 4, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_skewed_parallelepiped_reference_spectrum_and_residuals(tmp_path: Path) -> None:
    """Skewed cavity eigenvalues, M-orthonormality, and residuals match the independent reference."""
    mesh = tmp_path / "skew.mesh"
    skewed_parallelepiped_mesh().write(mesh)
    payload = _solve(mesh, 6, tmp_path / "out.json")
    ref = build_reference_solution(mesh, 6)
    _compare_payload_to_reference(mesh, 6, payload)
    M = ref["M"]
    vecs = np.column_stack([np.asarray(m["coefficients"]) for m in payload["modes"]])
    assert np.max(np.abs(mass_orthonormality_residual(M, vecs))) <= 1e-5
    vectors = [np.asarray(m["coefficients"]) for m in payload["modes"]]
    alg = recompute_algebraic_residuals(ref["K"], ref["M"], [m["eigenvalue"] for m in payload["modes"]], vectors)
    div = recompute_divergence_residuals(ref["mesh"], ref["topology"], vectors, M=ref["M"])
    for mode, a, d in zip(payload["modes"], alg, div):
        assert mode["residuals"]["algebraic"] <= ALGEBRAIC_TOL
        assert a <= ALGEBRAIC_TOL
        assert mode["residuals"]["divergence"] <= DIVERGENCE_TOL
        assert d <= DIVERGENCE_TOL


def test_two_cell_rectangular_cavity_reference_spectrum(tmp_path: Path) -> None:
    """Two-cell rectangular cavity matches reference spectra, DOFs, and coefficient lengths."""
    mesh = tmp_path / "two.mesh"
    two_cell_rectangular_cavity_mesh().write(mesh)
    payload = _solve(mesh, 6, tmp_path / "out.json")
    ref = build_reference_solution(mesh, 6)
    assert payload["active_dofs"] == ref["topology"].num_active_dofs
    assert all(len(m["coefficients"]) == payload["active_dofs"] for m in payload["modes"])
    _compare_payload_to_reference(mesh, 6, payload)
    vectors = [np.asarray(m["coefficients"]) for m in payload["modes"]]
    alg = recompute_algebraic_residuals(ref["K"], ref["M"], [m["eigenvalue"] for m in payload["modes"]], vectors)
    assert all(a <= ALGEBRAIC_TOL for a in alg)


def test_near_degenerate_valid_tetrahedra_remain_finite_and_positive(tmp_path: Path) -> None:
    """Numerically thin but valid meshes report finite positive modes within residual limits."""
    mesh = tmp_path / "thin.mesh"
    near_degenerate_valid_cavity_mesh().write(mesh)
    payload = _solve(mesh, 4, tmp_path / "out.json")
    scale = max(1.0, max(abs(m["eigenvalue"]) for m in payload["modes"]))
    assert all(m["eigenvalue"] > ZERO_TOL * scale for m in payload["modes"])
    for mode in payload["modes"]:
        assert all(math.isfinite(c) for c in mode["coefficients"])


def test_duplicate_coordinate_vertices_are_rejected_atomically(tmp_path: Path) -> None:
    """Meshes with duplicate vertex coordinates are rejected without clobbering output."""
    mesh = tmp_path / "dup.mesh"
    duplicate_coordinate_mesh().write(mesh)
    out = tmp_path / "out.json"
    write_sentinel(out)
    proc = run_solver(mesh, 4, out)
    _assert_failed_without_valid_modes(proc, out)
    assert sentinel_unchanged(out)


def test_boundary_face_not_on_tetrahedron_is_rejected_atomically(tmp_path: Path) -> None:
    """Boundary faces that are not tetrahedron faces are rejected without clobbering output."""
    mesh = tmp_path / "bad.mesh"
    boundary_face_not_on_tetra_mesh().write(mesh)
    out = tmp_path / "out.json"
    write_sentinel(out)
    proc = run_solver(mesh, 4, out)
    _assert_failed_without_valid_modes(proc, out)
    assert sentinel_unchanged(out)


def _combined_representation_mesh(base_mesh):
    """Heavy numbering/orientation/boundary transform preserving coordinates."""
    return combined_transform(
        base_mesh,
        vertex_perm=deterministic_perm(len(base_mesh.vertices) - 1, seed=88),
        element_order=list(reversed(range(len(base_mesh.elements)))),
        local_seed=19,
        boundary_order=list(reversed(range(len(base_mesh.boundary)))),
        reverse_faces=list(range(1, len(base_mesh.boundary), 2)),
    )


def test_canonical_coefficients_across_representation_transforms(tmp_path: Path) -> None:
    """Six-mode canonical coefficient arrays match across representation-only transforms."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "canonical.mesh"
    xform_mesh = tmp_path / "combined.mesh"
    base.write(ref_mesh)
    _combined_representation_mesh(base).write(xform_mesh)
    pa = _solve(ref_mesh, 6, tmp_path / "ref.json")
    pb = _solve(xform_mesh, 6, tmp_path / "xform.json")
    ref = build_reference_solution(ref_mesh, 6)
    assert payloads_match_canonical_contract(pa["modes"], pb["modes"], ref["M"], ref["K"])
    for mode in pa["modes"] + pb["modes"]:
        assert first_significant_coeff_positive(mode["coefficients"])
    vecs = np.column_stack([np.asarray(m["coefficients"]) for m in pa["modes"]])
    assert check_m_orthonormal(vecs, ref["M"])


def test_repeated_clean_run_coefficient_determinism(tmp_path: Path) -> None:
    """Repeated six-mode clean solves yield identical physics payloads."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    a = _solve(mesh, 6, tmp_path / "a.json")
    b = _solve(mesh, 6, tmp_path / "b.json")
    assert compare_physics_payloads(a, b)
    for mode in a["modes"]:
        for key in ("algebraic", "boundary_trace", "divergence"):
            assert mode["residuals"][key] == pytest.approx(
                next(m for m in b["modes"] if m["index"] == mode["index"])["residuals"][key],
                rel=0.0,
                abs=1e-12,
            )


def test_checkpoint_vectors_match_canonical_output_basis(tmp_path: Path) -> None:
    """Checkpoint Ritz vectors equal emitted canonical coefficients with valid Rayleigh pairs."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    out = tmp_path / "modes.json"
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh, 6, out, checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    payload = load_modes(out)
    env = parse_checkpoint(ckpt)
    assert env.ritz_value_count == env.ritz_vector_count == env.requested_modes == 6
    ref = build_reference_solution(mesh, 6)
    for i, mode in enumerate(payload["modes"]):
        ck = np.asarray(env.ritz_vectors[i].coefficients, dtype=np.float64)
        outc = np.asarray(mode["coefficients"], dtype=np.float64)
        assert np.max(np.abs(ck - outc)) <= 1e-8
        rq = rayleigh_quotient(mesh, ck, K=ref["K"], M=ref["M"])
        assert abs(rq - env.ritz_values[i]) / max(abs(env.ritz_values[i]), 1.0) <= 1e-7
    vecs = np.column_stack([np.asarray(v.coefficients) for v in env.ritz_vectors])
    assert check_m_orthonormal(vecs, ref["M"])


def test_canonical_resume_across_equivalent_mesh(tmp_path: Path) -> None:
    """Resuming a transformed checkpoint on the canonical mesh matches a clean solve."""
    base = unit_cube_mesh()
    src_mesh = tmp_path / "transformed.mesh"
    dst_mesh = tmp_path / "canonical.mesh"
    _combined_representation_mesh(base).write(src_mesh)
    base.write(dst_mesh)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(src_mesh, 6, tmp_path / "partial.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    clean = _solve(dst_mesh, 6, tmp_path / "clean.json")
    resumed = _solve(dst_mesh, 6, tmp_path / "resumed.json", resume=ckpt)
    ref = build_reference_solution(dst_mesh, 6)
    assert payloads_match_canonical_contract(clean["modes"], resumed["modes"], ref["M"], ref["K"])


def test_checkpoint_mismatched_ritz_counts_rejected_atomically(tmp_path: Path) -> None:
    """Mismatched Ritz value and vector counts are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path, modes=6, after=3)
    env = parse_checkpoint(ckpt)
    vectors = [list(v.coefficients) for v in env.ritz_vectors]
    rewrite_with_updates(ckpt, ritz_vectors=vectors[:-1])
    out = tmp_path / "bad.json"
    write_sentinel(out)
    bad = run_solver(mesh, 6, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_requested_mode_count_disagreement_rejected_atomically(tmp_path: Path) -> None:
    """Header requested_modes disagreeing with Ritz counts is rejected atomically."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path, modes=6, after=3)
    rewrite_with_updates(ckpt, requested_modes=5)
    out = tmp_path / "bad.json"
    write_sentinel(out)
    bad = run_solver(mesh, 6, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_non_orthonormal_vectors_rejected_atomically(tmp_path: Path) -> None:
    """Linearly dependent checkpoint vectors are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path, modes=6, after=3)
    env = parse_checkpoint(ckpt)
    vectors = [list(v.coefficients) for v in env.ritz_vectors]
    vectors[1] = list(vectors[0])
    rewrite_with_updates(ckpt, ritz_vectors=vectors)
    out = tmp_path / "bad.json"
    write_sentinel(out)
    bad = run_solver(mesh, 6, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)


def test_checkpoint_rayleigh_inconsistent_pair_rejected_atomically(tmp_path: Path) -> None:
    """Rayleigh-inconsistent Ritz values are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = _checkpoint(mesh, tmp_path, modes=6, after=3)
    env = parse_checkpoint(ckpt)
    values = list(env.ritz_values)
    values[2] = values[2] * 1.37 + 0.25
    rewrite_with_updates(ckpt, ritz_values=values)
    out = tmp_path / "bad.json"
    write_sentinel(out)
    bad = run_solver(mesh, 6, out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, out)
    assert sentinel_unchanged(out)
