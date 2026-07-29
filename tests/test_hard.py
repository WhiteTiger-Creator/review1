"""Hardening verifier for /app/bin/emsolve.

Independent reference checks, geometric invariance sweeps, checkpoint integrity,
and atomic failure semantics. Complements ``test_outputs.py`` without duplicating
its baseline behavioral cases.

``rebuild_solver`` is defined here with the same session-scoped name as in
``test_outputs.py``; pytest deduplicates identical session fixtures when both
modules are collected together (see ``tests/test.sh``).
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from helpers.checkpoint_tools import (
    flip_byte,
    replace_bytes,
    sentinel_unchanged,
    truncate,
    write_sentinel,
)
from helpers.mesh_factory import (
    TETRA_VERTEX_PERMUTATIONS,
    MeshData,
    apply_local_vertex_perm,
    combined_transform,
    deterministic_perm,
    invalid_mesh_nonfinite_coordinate,
    invalid_mesh_unsupported_boundary_tag,
    mixed_local_permutations,
    permute_boundary_vertices,
    permute_coordinate_axes,
    permute_corner_vertices,
    reorder_boundary_faces,
    reorder_elements,
    reverse_boundary_winding,
    scale_uniform,
    stretched_cavity_mesh,
    translate_mesh,
    unit_cube_mesh,
)
from helpers.operator_checks import compare_clustered_spectra
from helpers.reference_nedelec import (
    ALGEBRAIC_TOL,
    BOUNDARY_TOL,
    CLUSTER_REL_GAP_TOL,
    DIVERGENCE_TOL,
    build_reference_solution,
    cluster_eigenvalues,
    mass_orthonormality_residual,
    recompute_algebraic_residuals,
    recompute_divergence_residuals,
    scale_law_check,
    verify_operator_properties,
)
from helpers.run_solver import load_modes, run_solver

APP_DIR = Path("/app")
DATA = APP_DIR / "data"
CANONICAL_MESH = DATA / "meshes" / "cavity_canonical.mesh"
DEFAULT_CONFIG = DATA / "configs" / "default.toml"
STRICT_CONFIG = DATA / "configs" / "strict.toml"
INVALID_NONMANIFOLD = DATA / "meshes" / "invalid_nonmanifold.mesh"

REF_VAL_RTOL = 1e-5
REF_ANGLE_TOL = 0.05
VERTEX_PERM_SEEDS = (3, 11, 17, 42, 99)
CHECKPOINT_BOUNDARIES = (1, 2, 3, 4)
CHECKPOINT_RESUME_SEEDS = (5, 23, 77)


def all_local_tetra_permutations() -> tuple[tuple[int, int, int, int], ...]:
    """Expose the 24 tetrahedron vertex permutations for parametrized sweeps."""
    return TETRA_VERTEX_PERMUTATIONS


def permute_element_local_vertices(
    mesh: MeshData, element_id: int, local_perm: Sequence[int]
) -> MeshData:
    """Apply one local tetrahedron vertex permutation to a single element."""
    return apply_local_vertex_perm(mesh, [element_id], local_perm)


def apply_seeded_mixed_local_permutations(mesh: MeshData, seed: int) -> MeshData:
    """Apply independent local permutations to every element."""
    return mixed_local_permutations(mesh, seed)


def apply_uniform_scale(mesh: MeshData, factor: float) -> MeshData:
    """Uniformly scale every vertex coordinate."""
    return scale_uniform(mesh, factor)


def permute_axes(mesh: MeshData, axis_perm: Sequence[int]) -> MeshData:
    """Relabel coordinate axes consistently across all vertices."""
    return permute_coordinate_axes(mesh, axis_perm)


def rotate_and_reverse_boundary_faces(mesh: MeshData) -> MeshData:
    """Rotate and reverse a deterministic subset of boundary faces."""
    rotated = permute_boundary_vertices(mesh, [1] * len(mesh.boundary))
    reverse_ids = list(range(1, len(mesh.boundary), 2))
    return reverse_boundary_winding(rotated, reverse_ids)


def reorder_boundary_faces_default(mesh: MeshData) -> MeshData:
    """Reorder the boundary-face list without changing geometry."""
    order = list(reversed(range(len(mesh.boundary))))
    return reorder_boundary_faces(mesh, order)


def apply_combined_transform(
    mesh: MeshData,
    *,
    vertex_seed: int = 17,
    local_perm_seed: int = 5,
) -> MeshData:
    """Apply a heavy combined representational transform."""
    n_corner = len(mesh.vertices) - 1
    return combined_transform(
        mesh,
        vertex_perm=deterministic_perm(n_corner, seed=vertex_seed),
        element_order=list(reversed(range(len(mesh.elements)))),
        local_seed=local_perm_seed,
        boundary_order=list(reversed(range(len(mesh.boundary)))),
        reverse_faces=list(range(1, len(mesh.boundary), 2)),
    )


def alternate_connectivity_unit_cube() -> MeshData:
    """Same vertex coordinates as the unit cube with different tet connectivity."""
    base = unit_cube_mesh()
    elems = list(base.elements)
    # Replace a center-based tet with a corner tet so the physical connectivity changes.
    elems[0] = (0, 1, 2, 3)
    elems[1] = (4, 5, 6, 7)
    return MeshData(base.vertices, elems, base.boundary)


def invalid_mesh_cases() -> list[tuple[str, MeshData | str | Path]]:
    """Matrix of invalid meshes for atomic rejection tests."""
    truncated_text = (
        "emsolve-mesh 1\nvertices 2\n0 0 0 0\n1 1 0 0\n"
    )
    out_of_range_text = (
        "emsolve-mesh 1\n"
        "vertices 9\n"
        "0 0.0 0.0 0.0\n1 1.0 0.0 0.0\n2 0.0 1.0 0.0\n3 0.0 0.0 1.0\n"
        "4 1.0 1.0 0.0\n5 1.0 0.0 1.0\n6 0.0 1.0 1.0\n7 1.0 1.0 1.0\n8 0.5 0.5 0.5\n"
        "elements 1\n0 0 1 2 99\n"
        "boundary 1\n0 0 1 2 pec\n"
    )
    duplicate_text = (
        "emsolve-mesh 1\n"
        "vertices 9\n0 0 0 0\n0 0 0 0\n1 1.0 0.0 0.0\n2 0.0 1.0 0.0\n3 0.0 0.0 1.0\n"
        "4 1.0 1.0 0.0\n5 1.0 0.0 1.0\n6 0.0 1.0 1.0\n7 1.0 1.0 1.0\n8 0.5 0.5 0.5\n"
        "elements 1\n0 0 1 2 3\nboundary 1\n0 0 1 2 pec\n"
    )
    return [
        ("truncated", truncated_text),
        ("duplicate_vertex_id", duplicate_text),
        ("out_of_range_vertex", out_of_range_text),
        ("nan_coordinate", invalid_mesh_nonfinite_coordinate()),
        ("unsupported_boundary_tag", invalid_mesh_unsupported_boundary_tag()),
        ("nonmanifold", INVALID_NONMANIFOLD),
    ]


@pytest.fixture(scope="session", autouse=True)
def rebuild_solver() -> None:
    """Force a clean rebuild so patched sources are exercised."""
    shutil.rmtree("/app/build", ignore_errors=True)
    subprocess.run(["/app/scripts/build.sh"], check=True)


def _assert_residuals(payload: dict) -> None:
    for mode in payload["modes"]:
        res = mode["residuals"]
        assert res["boundary_trace"] <= BOUNDARY_TOL
        assert res["divergence"] <= DIVERGENCE_TOL
        assert res["algebraic"] <= ALGEBRAIC_TOL


def _solve(mesh: Path, modes: int, output: Path, **kwargs: Any) -> dict:
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


def _mass_orthonormalize(M: np.ndarray, vecs: np.ndarray) -> np.ndarray:
    evals, evecs = np.linalg.eigh(M)
    evals = np.maximum(evals, 1e-30)
    inv_sqrt = evecs @ np.diag(1.0 / np.sqrt(evals)) @ evecs.T
    return inv_sqrt @ vecs


def _mass_principal_angles(M: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    qa, _ = np.linalg.qr(_mass_orthonormalize(M, A))
    qb, _ = np.linalg.qr(_mass_orthonormalize(M, B))
    s = np.linalg.svd(qa.T @ qb, compute_uv=False)
    s = np.clip(s, -1.0, 1.0)
    return np.arccos(s)


def _compare_payload_to_reference(
    mesh: Path | MeshData,
    modes: int,
    payload: dict,
    *,
    ref: dict | None = None,
    angle_tol: float = REF_ANGLE_TOL,
) -> None:
    """Match candidate output against the independent Nedelec reference."""
    if ref is None:
        ref_n = max(modes, 6)
        ref_full = build_reference_solution(mesh, ref_n)
        ref = ref_full
    vals_cand = np.array([m["eigenvalue"] for m in payload["modes"]], dtype=float)
    ref_vals_all = np.asarray(ref["eigenvalues"], dtype=float)
    ref_coeffs_all = ref["coefficients"]

    pairs: list[int] = []
    used: set[int] = set()
    for lam in vals_cand:
        best_j = None
        best_d = float("inf")
        for j, lam_r in enumerate(ref_vals_all):
            if j in used:
                continue
            d = abs(float(lam) - float(lam_r))
            if d < best_d:
                best_d = d
                best_j = j
        assert best_j is not None
        assert best_d <= REF_VAL_RTOL * max(1.0, abs(float(lam)))
        used.add(best_j)
        pairs.append(best_j)

    vals_ref = np.array([float(ref_vals_all[j]) for j in pairs], dtype=float)
    assert np.allclose(vals_cand, vals_ref, rtol=REF_VAL_RTOL, atol=0.0)

    if modes < 6:
        return

    vecs_ref = np.column_stack([np.asarray(ref_coeffs_all[j]) for j in pairs])
    vecs_cand = np.column_stack([np.asarray(m["coefficients"]) for m in payload["modes"]])
    assert compare_clustered_spectra(
        vals_ref.tolist(),
        [vecs_ref[:, i] for i in range(vecs_ref.shape[1])],
        vals_cand.tolist(),
        [vecs_cand[:, i] for i in range(vecs_cand.shape[1])],
        val_tol=REF_VAL_RTOL,
        angle_tol=angle_tol,
    )


def _cluster_ids_from_values(values: Sequence[float]) -> list[int]:
    clusters = cluster_eigenvalues(values, tol=CLUSTER_REL_GAP_TOL)
    out = [0] * len(values)
    for cid, members in enumerate(clusters):
        for idx in members:
            out[idx] = cid
    return out


def _spectra_equivalent(mesh_a: Path, modes: int, mesh_b: Path, out_a: Path, out_b: Path) -> None:
    pa = _solve(mesh_a, modes, out_a)
    pb = _solve(mesh_b, modes, out_b)
    assert pa["active_dofs"] == pb["active_dofs"]
    va = [m["eigenvalue"] for m in pa["modes"]]
    vb = [m["eigenvalue"] for m in pb["modes"]]
    assert np.allclose(va, vb, rtol=REF_VAL_RTOL, atol=0.0)


def test_reference_nedelec_spectrum_on_unit_cube(tmp_path: Path) -> None:
    """Independent Nedelec reference matches the solver on a unit cube."""
    mesh = tmp_path / "unit.mesh"
    unit_cube_mesh().write(mesh)
    payload = _solve(mesh, 6, tmp_path / "out.json")
    _compare_payload_to_reference(mesh, 6, payload)


def test_reference_nedelec_spectrum_on_stretched_cavity(tmp_path: Path) -> None:
    """Independent reference tracks a non-cubic cavity geometry."""
    mesh = tmp_path / "stretched.mesh"
    stretched_cavity_mesh((1.3, 0.9, 1.1)).write(mesh)
    payload = _solve(mesh, 6, tmp_path / "out.json")
    _compare_payload_to_reference(mesh, 6, payload)


def test_reported_algebraic_residual_matches_independent_operator(tmp_path: Path) -> None:
    """Reported algebraic residuals agree with K/M recomputation."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    payload = _solve(mesh, 4, tmp_path / "out.json")
    ref = build_reference_solution(mesh, 4)
    K, M = ref["K"], ref["M"]
    lambdas = [m["eigenvalue"] for m in payload["modes"]]
    vectors = [np.asarray(m["coefficients"]) for m in payload["modes"]]
    independent = recompute_algebraic_residuals(K, M, lambdas, vectors)
    for mode, expected in zip(payload["modes"], independent):
        assert abs(mode["residuals"]["algebraic"] - expected) <= max(ALGEBRAIC_TOL, 1e-9)


def test_modes_are_mass_orthonormal(tmp_path: Path) -> None:
    """Mode blocks are M-orthonormal within tolerance."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    payload = _solve(mesh, 6, tmp_path / "out.json")
    ref = build_reference_solution(mesh, 6)
    M = ref["M"]
    vecs = np.column_stack([np.asarray(m["coefficients"]) for m in payload["modes"]])
    residual = mass_orthonormality_residual(M, vecs)
    assert np.max(np.abs(residual)) <= 1e-5


def test_modes_are_discrete_divergence_free(tmp_path: Path) -> None:
    """Reported and recomputed divergence residuals stay below contract limits."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    payload = _solve(mesh, 6, tmp_path / "out.json")
    ref = build_reference_solution(mesh, 6)
    vectors = [np.asarray(m["coefficients"]) for m in payload["modes"]]
    independent = recompute_divergence_residuals(ref["mesh"], ref["topology"], vectors, M=ref["M"])
    for mode, expected in zip(payload["modes"], independent):
        assert mode["residuals"]["divergence"] <= DIVERGENCE_TOL
        assert expected <= DIVERGENCE_TOL


def test_uniform_scale_inverse_square_law(tmp_path: Path) -> None:
    """Uniform scaling follows lambda -> lambda / s^2."""
    base_mesh = tmp_path / "base.mesh"
    scaled_mesh = tmp_path / "scaled.mesh"
    scale = 1.7
    unit_cube_mesh().write(base_mesh)
    apply_uniform_scale(unit_cube_mesh(), scale).write(scaled_mesh)
    base_payload = _solve(base_mesh, 4, tmp_path / "base.json")
    scaled_payload = _solve(scaled_mesh, 4, tmp_path / "scaled.json")
    base_ref = build_reference_solution(base_mesh, 4)
    scaled_ref = build_reference_solution(scaled_mesh, 4)
    result = scale_law_check(
        base_ref["mesh"],
        scaled_ref["mesh"],
        scale,
        {"eigenvalues": base_ref["eigenvalues"]},
        {"eigenvalues": scaled_ref["eigenvalues"]},
        rtol=1e-4,
    )
    assert result["passed"]
    result_solver = scale_law_check(
        base_mesh,
        scaled_mesh,
        scale,
        {"eigenvalues": [m["eigenvalue"] for m in base_payload["modes"]]},
        {"eigenvalues": [m["eigenvalue"] for m in scaled_payload["modes"]]},
        rtol=1e-4,
    )
    assert result_solver["passed"]


def test_active_dof_and_coefficient_order_match_canonical_edge_contract(tmp_path: Path) -> None:
    """active_dofs and coefficient slots follow the canonical edge ordering."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    payload = _solve(mesh, 4, tmp_path / "out.json")
    ref_full = build_reference_solution(mesh, 6)
    ref = ref_full
    topo = ref["topology"]
    assert payload["active_dofs"] == topo.num_active_dofs
    props = verify_operator_properties(ref["K"], ref["M"])
    assert props["k_is_psd"] and props["m_is_pd"]
    for mode in payload["modes"]:
        assert len(mode["coefficients"]) == topo.num_active_dofs
    _compare_payload_to_reference(mesh, 4, payload, ref=ref)


def test_cluster_ids_match_documented_relative_gap_rule(tmp_path: Path) -> None:
    """cluster_id fields follow the documented relative-gap clustering rule."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    payload = _solve(mesh, 6, tmp_path / "out.json")
    values = [m["eigenvalue"] for m in payload["modes"]]
    expected = _cluster_ids_from_values(values)
    reported = [m["cluster_id"] for m in payload["modes"]]
    assert reported == expected


@pytest.mark.parametrize("seed", VERTEX_PERM_SEEDS)
def test_multiple_global_vertex_renumberings_preserve_canonical_payload(
    tmp_path: Path, seed: int
) -> None:
    """Several global vertex permutations leave the canonical physics payload unchanged."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / f"ref_{seed}.mesh"
    xform_mesh = tmp_path / f"xform_{seed}.mesh"
    base.write(ref_mesh)
    permute_corner_vertices(base, deterministic_perm(len(base.vertices) - 1, seed=seed)).write(
        xform_mesh
    )
    _spectra_equivalent(ref_mesh, 4, xform_mesh, tmp_path / f"a_{seed}.json", tmp_path / f"b_{seed}.json")


def test_multiple_element_orderings_preserve_canonical_payload(tmp_path: Path) -> None:
    """Multiple element permutations preserve spectra and coefficient subspaces."""
    base = unit_cube_mesh()
    orders = [
        list(reversed(range(len(base.elements)))),
        deterministic_perm(len(base.elements), seed=2),
        deterministic_perm(len(base.elements), seed=31),
    ]
    ref_mesh = tmp_path / "ref.mesh"
    base.write(ref_mesh)
    pa = _solve(ref_mesh, 4, tmp_path / "ref.json")
    for idx, order in enumerate(orders):
        mesh = tmp_path / f"order_{idx}.mesh"
        reorder_elements(base, order).write(mesh)
        pb = _solve(mesh, 4, tmp_path / f"out_{idx}.json")
        assert compare_clustered_spectra(
            [m["eigenvalue"] for m in pa["modes"]],
            [m["coefficients"] for m in pa["modes"]],
            [m["eigenvalue"] for m in pb["modes"]],
            [m["coefficients"] for m in pb["modes"]],
            val_tol=REF_VAL_RTOL,
            angle_tol=REF_ANGLE_TOL,
        )


@pytest.mark.parametrize("local_perm", all_local_tetra_permutations())
def test_all_local_tetra_permutation_parities_preserve_spectrum(
    tmp_path: Path, local_perm: tuple[int, int, int, int]
) -> None:
    """Every one of the 24 local tetrahedron vertex permutations preserves the spectrum."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / f"perm_{''.join(map(str, local_perm))}.mesh"
    base.write(ref_mesh)
    transformed = base
    for eid in range(len(base.elements)):
        transformed = permute_element_local_vertices(transformed, eid, local_perm)
    transformed.write(xform_mesh)
    _spectra_equivalent(ref_mesh, 2, xform_mesh, tmp_path / "ref.json", tmp_path / "xform.json")


def test_seeded_mixed_local_permutations_preserve_modes(tmp_path: Path) -> None:
    """Independent per-element local permutations preserve physical modes."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / "mixed.mesh"
    base.write(ref_mesh)
    apply_seeded_mixed_local_permutations(base, seed=12345).write(xform_mesh)
    _spectra_equivalent(ref_mesh, 4, xform_mesh, tmp_path / "ref.json", tmp_path / "xform.json")


def test_boundary_face_rotations_and_reversals_preserve_modes(tmp_path: Path) -> None:
    """Boundary-face rotations and orientation reversals do not change modes."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / "boundary.mesh"
    base.write(ref_mesh)
    rotate_and_reverse_boundary_faces(base).write(xform_mesh)
    _spectra_equivalent(ref_mesh, 4, xform_mesh, tmp_path / "ref.json", tmp_path / "xform.json")


def test_boundary_face_list_reordering_preserves_modes(tmp_path: Path) -> None:
    """Reordering the boundary-face list leaves spectra unchanged."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / "boundary_order.mesh"
    base.write(ref_mesh)
    reorder_boundary_faces_default(base).write(xform_mesh)
    _spectra_equivalent(ref_mesh, 4, xform_mesh, tmp_path / "ref.json", tmp_path / "xform.json")


def test_rigid_translation_preserves_physical_spectrum(tmp_path: Path) -> None:
    """Translating the cavity preserves eigenvalues and coefficient subspaces."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / "translated.mesh"
    base.write(ref_mesh)
    translate_mesh(base, (10.0, -3.5, 2.25)).write(xform_mesh)
    _spectra_equivalent(ref_mesh, 4, xform_mesh, tmp_path / "ref.json", tmp_path / "xform.json")


def test_axis_permutation_preserves_physical_spectrum(tmp_path: Path) -> None:
    """Consistent axis relabeling preserves the physical spectrum."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / "axes.mesh"
    base.write(ref_mesh)
    permute_axes(base, (2, 0, 1)).write(xform_mesh)
    _spectra_equivalent(ref_mesh, 4, xform_mesh, tmp_path / "ref.json", tmp_path / "xform.json")


def test_combined_numbering_element_orientation_boundary_transform(tmp_path: Path) -> None:
    """A combined representational transform preserves canonical physics."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / "combined.mesh"
    base.write(ref_mesh)
    apply_combined_transform(base).write(xform_mesh)
    _spectra_equivalent(ref_mesh, 4, xform_mesh, tmp_path / "ref.json", tmp_path / "xform.json")


def test_combined_transform_six_mode_cluster_subspace(tmp_path: Path) -> None:
    """Six-mode clustered subspaces survive a heavy combined mesh transform."""
    base = unit_cube_mesh()
    ref_mesh = tmp_path / "ref.mesh"
    xform_mesh = tmp_path / "combined.mesh"
    base.write(ref_mesh)
    apply_combined_transform(base, vertex_seed=88, local_perm_seed=19).write(xform_mesh)
    pa = _solve(ref_mesh, 6, tmp_path / "ref.json")
    pb = _solve(xform_mesh, 6, tmp_path / "xform.json")
    assert compare_clustered_spectra(
        [m["eigenvalue"] for m in pa["modes"]],
        [m["coefficients"] for m in pa["modes"]],
        [m["eigenvalue"] for m in pb["modes"]],
        [m["coefficients"] for m in pb["modes"]],
        val_tol=REF_VAL_RTOL,
        angle_tol=0.08,
    )


@pytest.mark.parametrize("checkpoint_after", CHECKPOINT_BOUNDARIES)
def test_checkpoint_resume_at_multiple_iteration_boundaries(
    tmp_path: Path, checkpoint_after: int
) -> None:
    """Checkpoint/resume matches a clean solve for several iteration boundaries."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    clean = _solve(mesh, 4, tmp_path / "clean.json")
    ckpt = tmp_path / f"ckpt_{checkpoint_after}.bin"
    partial_out = tmp_path / f"partial_{checkpoint_after}.json"
    proc = run_solver(mesh, 4, partial_out, checkpoint=ckpt, checkpoint_after=checkpoint_after)
    assert proc.returncode == 0, proc.stderr
    resumed = _solve(mesh, 4, tmp_path / f"resumed_{checkpoint_after}.json", resume=ckpt)
    assert compare_clustered_spectra(
        [m["eigenvalue"] for m in clean["modes"]],
        [m["coefficients"] for m in clean["modes"]],
        [m["eigenvalue"] for m in resumed["modes"]],
        [m["coefficients"] for m in resumed["modes"]],
        val_tol=REF_VAL_RTOL,
        angle_tol=REF_ANGLE_TOL,
    )


@pytest.mark.parametrize("seed", CHECKPOINT_RESUME_SEEDS)
def test_checkpoint_resume_on_vertex_renumbered_mesh_multiple_seeds(
    tmp_path: Path, seed: int
) -> None:
    """Checkpoints resume on globally renumbered but equivalent meshes."""
    base = unit_cube_mesh()
    mesh_a = tmp_path / f"a_{seed}.mesh"
    mesh_b = tmp_path / f"b_{seed}.mesh"
    base.write(mesh_a)
    permute_corner_vertices(base, deterministic_perm(len(base.vertices) - 1, seed=seed)).write(
        mesh_b
    )
    ckpt = tmp_path / f"ckpt_{seed}.bin"
    proc = run_solver(mesh_a, 4, tmp_path / f"seed_{seed}.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    direct = _solve(mesh_b, 4, tmp_path / f"direct_{seed}.json")
    resumed = _solve(mesh_b, 4, tmp_path / f"resumed_{seed}.json", resume=ckpt)
    assert compare_clustered_spectra(
        [m["eigenvalue"] for m in direct["modes"]],
        [m["coefficients"] for m in direct["modes"]],
        [m["eigenvalue"] for m in resumed["modes"]],
        [m["coefficients"] for m in resumed["modes"]],
        val_tol=REF_VAL_RTOL,
        angle_tol=REF_ANGLE_TOL,
    )


def test_checkpoint_resume_on_combined_equivalent_mesh(tmp_path: Path) -> None:
    """A checkpoint taken on a reference mesh resumes on a combined transform."""
    base = unit_cube_mesh()
    mesh_a = tmp_path / "a.mesh"
    mesh_b = tmp_path / "b.mesh"
    base.write(mesh_a)
    apply_combined_transform(base).write(mesh_b)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh_a, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=2)
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


def test_checkpoint_resume_preserves_reference_residuals_and_orthonormality(tmp_path: Path) -> None:
    """Resumed runs keep reference-grade residuals and M-orthonormality."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh, 6, tmp_path / "partial.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    payload = _solve(mesh, 6, tmp_path / "resumed.json", resume=ckpt)
    ref = build_reference_solution(mesh, 6)
    _compare_payload_to_reference(mesh, 6, payload, ref=ref)
    M = ref["M"]
    vecs = np.column_stack([np.asarray(m["coefficients"]) for m in payload["modes"]])
    assert np.max(np.abs(mass_orthonormality_residual(M, vecs))) <= 1e-5


def test_checkpoint_rejects_same_dof_different_geometry_atomically(tmp_path: Path) -> None:
    """Incompatible geometry with matching active_dof count is rejected without clobbering output."""
    mesh_a = tmp_path / "a.mesh"
    mesh_b = tmp_path / "b.mesh"
    unit_cube_mesh().write(mesh_a)
    stretched_cavity_mesh((1.25, 1.0, 1.0)).write(mesh_b)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh_a, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    bad_out = tmp_path / "bad.json"
    write_sentinel(bad_out)
    bad = run_solver(mesh_b, 4, bad_out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, bad_out)
    assert sentinel_unchanged(bad_out)


def test_checkpoint_rejects_same_geometry_different_connectivity_atomically(tmp_path: Path) -> None:
    """Different connectivity with the same vertex coordinates is rejected atomically."""
    mesh_a = tmp_path / "a.mesh"
    mesh_b = tmp_path / "b.mesh"
    unit_cube_mesh().write(mesh_a)
    alternate_connectivity_unit_cube().write(mesh_b)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh_a, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    bad_out = tmp_path / "bad.json"
    write_sentinel(bad_out)
    bad = run_solver(mesh_b, 4, bad_out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, bad_out)
    assert sentinel_unchanged(bad_out)


def test_checkpoint_truncation_rejected_atomically(tmp_path: Path) -> None:
    """Truncated checkpoint files are rejected without touching existing output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    nbytes = max(32, len(ckpt.read_bytes()) // 2)
    truncate(ckpt, nbytes)
    bad_out = tmp_path / "bad.json"
    write_sentinel(bad_out)
    bad = run_solver(mesh, 4, bad_out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, bad_out)
    assert sentinel_unchanged(bad_out)


def test_checkpoint_bitflip_rejected_atomically(tmp_path: Path) -> None:
    """Single-byte corruption in a checkpoint is rejected atomically."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    flip_byte(ckpt, 32)
    bad_out = tmp_path / "bad.json"
    write_sentinel(bad_out)
    bad = run_solver(mesh, 4, bad_out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, bad_out)
    assert sentinel_unchanged(bad_out)


def test_checkpoint_header_version_mutation_rejected_atomically(tmp_path: Path) -> None:
    """Unsupported checkpoint versions are rejected without clobbering output."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    ckpt = tmp_path / "state.bin"
    proc = run_solver(mesh, 4, tmp_path / "seed.json", checkpoint=ckpt, checkpoint_after=3)
    assert proc.returncode == 0, proc.stderr
    replace_bytes(ckpt, 4, struct.pack("<I", 2))
    bad_out = tmp_path / "bad.json"
    write_sentinel(bad_out)
    bad = run_solver(mesh, 4, bad_out, resume=ckpt)
    _assert_failed_without_valid_modes(bad, bad_out)
    assert sentinel_unchanged(bad_out)


@pytest.mark.parametrize("case_name,invalid_mesh", invalid_mesh_cases())
def test_invalid_mesh_matrix_rejected_without_clobbering_output(
    tmp_path: Path, case_name: str, invalid_mesh: MeshData | str | Path
) -> None:
    """Invalid meshes fail fast and never overwrite an existing output file."""
    if isinstance(invalid_mesh, Path):
        mesh_path = invalid_mesh
    elif isinstance(invalid_mesh, MeshData):
        mesh_path = tmp_path / f"{case_name}.mesh"
        invalid_mesh.write(mesh_path)
    elif isinstance(invalid_mesh, str) and invalid_mesh.startswith("emsolve-mesh"):
        mesh_path = tmp_path / f"{case_name}.mesh"
        mesh_path.write_text(invalid_mesh, encoding="utf-8")
    else:
        raise TypeError(f"unsupported invalid mesh fixture for {case_name!r}")
    out = tmp_path / f"bad_{case_name}.json"
    write_sentinel(out)
    proc = run_solver(mesh_path, 4, out)
    _assert_failed_without_valid_modes(proc, out)
    assert sentinel_unchanged(out)


def test_repeated_clean_and_resume_outputs_are_deterministic(tmp_path: Path) -> None:
    """Repeated clean and checkpoint-resume runs yield identical mode payloads."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)

    def run_once(tag: str) -> dict:
        clean = _solve(mesh, 4, tmp_path / f"{tag}_clean.json")
        ckpt = tmp_path / f"{tag}.bin"
        proc = run_solver(mesh, 4, tmp_path / f"{tag}_partial.json", checkpoint=ckpt, checkpoint_after=3)
        assert proc.returncode == 0, proc.stderr
        resumed = _solve(mesh, 4, tmp_path / f"{tag}_resumed.json", resume=ckpt)
        return {"clean": clean, "resumed": resumed}

    first = run_once("a")
    second = run_once("b")
    for label in ("clean", "resumed"):
        pa, pb = first[label], second[label]
        assert pa["active_dofs"] == pb["active_dofs"]
        assert compare_clustered_spectra(
            [m["eigenvalue"] for m in pa["modes"]],
            [m["coefficients"] for m in pa["modes"]],
            [m["eigenvalue"] for m in pb["modes"]],
            [m["coefficients"] for m in pb["modes"]],
            val_tol=REF_VAL_RTOL,
            angle_tol=REF_ANGLE_TOL,
        )


def test_config_and_mode_count_preserve_reference_physics(tmp_path: Path) -> None:
    """Config files and several mode counts preserve reference eigenphysics."""
    mesh = tmp_path / "mesh.mesh"
    unit_cube_mesh().write(mesh)
    for modes in (4, 6):
        for config in (None, DEFAULT_CONFIG, STRICT_CONFIG):
            out = tmp_path / f"m{modes}_{'default' if config is None else config.stem}.json"
            kwargs: dict[str, Any] = {}
            if config is not None:
                kwargs["config"] = config
            payload = _solve(mesh, modes, out, **kwargs)
            assert payload["requested_modes"] == modes
            _compare_payload_to_reference(mesh, modes, payload)
