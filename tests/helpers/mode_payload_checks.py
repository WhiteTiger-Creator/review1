"""Coefficient-level mode payload checks for canonical basis contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from helpers.reference_nedelec import (
    CLUSTER_REL_GAP_TOL,
    build_reference_solution,
    cluster_eigenvalues,
    mass_orthonormality_residual,
)
from scipy.sparse import csr_matrix

COEFF_TOL = 1e-8
M_ORTHONORM_TOL = 1e-8
RAYLEIGH_REL_TOL = 1e-7
REPEATED_SUBGROUP_TOL = 1e-10


def rayleigh_quotient(
    mesh: Path | Any,
    coeffs: Sequence[float] | np.ndarray,
    K: csr_matrix | None = None,
    M: csr_matrix | None = None,
) -> float:
    """Compute x^T K x / x^T M x for a reduced coefficient vector."""
    if K is None or M is None:
        ref = build_reference_solution(mesh, 1)
        K = ref["K"]
        M = ref["M"]
    x = np.asarray(coeffs, dtype=np.float64)
    mxx = float(x @ (M @ x))
    if mxx <= 0.0:
        raise ValueError("non-positive M-norm for Rayleigh quotient")
    return float(x @ (K @ x) / mxx)


def m_inner_product(
    coeffs_a: Sequence[float] | np.ndarray,
    coeffs_b: Sequence[float] | np.ndarray,
    M: csr_matrix,
) -> float:
    """Mass inner product between two reduced coefficient vectors."""
    a = np.asarray(coeffs_a, dtype=np.float64)
    b = np.asarray(coeffs_b, dtype=np.float64)
    return float(a @ (M @ b))


def check_m_orthonormal(
    vectors: Sequence[Sequence[float]] | np.ndarray,
    M: csr_matrix,
    *,
    tol: float = M_ORTHONORM_TOL,
) -> bool:
    """Return True when columns are M-orthonormal within tolerance."""
    vecs = np.asarray(vectors, dtype=np.float64)
    if vecs.ndim == 1:
        vecs = vecs.reshape(-1, 1)
    residual = mass_orthonormality_residual(M, vecs)
    return bool(np.max(np.abs(residual)) <= tol)


def first_significant_coeff_positive(
    coeffs: Sequence[float] | np.ndarray,
    *,
    threshold: float = 1e-12,
) -> bool:
    """Sign rule: first coefficient with magnitude > threshold is positive."""
    for c in coeffs:
        if abs(float(c)) > threshold:
            return float(c) > 0.0
    return True


def compare_mode_coefficients_elementwise(
    coeffs_a: Sequence[float] | np.ndarray,
    coeffs_b: Sequence[float] | np.ndarray,
    *,
    tol: float = COEFF_TOL,
) -> bool:
    """Elementwise coefficient equality within tolerance."""
    a = np.asarray(coeffs_a, dtype=np.float64)
    b = np.asarray(coeffs_b, dtype=np.float64)
    if a.shape != b.shape:
        return False
    return bool(np.max(np.abs(a - b)) <= tol)


def _repeated_subgroups_from_cluster(
    values: Sequence[float],
    cluster_members: Sequence[int],
) -> list[list[int]]:
    """Split one cluster_id group into repeated subgroups (Section 4a rule)."""
    members = sorted(cluster_members, key=lambda i: values[i])
    if not members:
        return []
    groups: list[list[int]] = []
    cur = [members[0]]
    lam0 = float(values[members[0]])
    scale = max(1.0, abs(lam0))
    for idx in members[1:]:
        lam = float(values[idx])
        if max(abs(lam - lam0), abs(lam - float(values[cur[0]]))) <= REPEATED_SUBGROUP_TOL * scale:
            cur.append(idx)
        else:
            groups.append(cur)
            cur = [idx]
            lam0 = lam
            scale = max(1.0, abs(lam0))
    groups.append(cur)
    return groups


def _cluster_ids_from_payload(modes: Sequence[Mapping[str, Any]]) -> list[int]:
    return [int(m["cluster_id"]) for m in modes]


def _cluster_members(cluster_ids: Sequence[int], cid: int) -> list[int]:
    return [i for i, c in enumerate(cluster_ids) if c == cid]


def compare_physics_payloads(
    a: Mapping[str, Any],
    b: Mapping[str, Any],
    *,
    exclude_mesh_path: bool = True,
    coeff_tol: float = COEFF_TOL,
) -> bool:
    """Compare eigenvalues, cluster_ids, and elementwise coefficients."""
    del exclude_mesh_path  # payloads never carry mesh paths in modes.json
    if a.get("active_dofs") != b.get("active_dofs"):
        return False
    modes_a = list(a.get("modes", []))
    modes_b = list(b.get("modes", []))
    if len(modes_a) != len(modes_b):
        return False
    vals_a = [float(m["eigenvalue"]) for m in modes_a]
    vals_b = [float(m["eigenvalue"]) for m in modes_b]
    if not np.allclose(vals_a, vals_b, rtol=RAYLEIGH_REL_TOL, atol=0.0):
        return False
    cids_a = _cluster_ids_from_payload(modes_a)
    cids_b = _cluster_ids_from_payload(modes_b)
    if cids_a != cids_b:
        return False
    for i in range(len(modes_a)):
        if not compare_mode_coefficients_elementwise(
            modes_a[i]["coefficients"],
            modes_b[i]["coefficients"],
            tol=coeff_tol,
        ):
            return False
    return True


def check_payload_canonical_sign_and_orthonormality(
    payload: Mapping[str, Any],
    mesh: Path | Any,
    *,
    orth_tol: float = M_ORTHONORM_TOL,
) -> bool:
    """Verify sign rule and M-orthonormality for a modes payload."""
    ref = build_reference_solution(mesh, max(int(payload.get("computed_modes", 1)), 1))
    M = ref["M"]
    modes = list(payload.get("modes", []))
    for mode in modes:
        if not first_significant_coeff_positive(mode["coefficients"]):
            return False
    vecs = np.column_stack([np.asarray(m["coefficients"], dtype=np.float64) for m in modes])
    if not check_m_orthonormal(vecs, M, tol=orth_tol):
        return False
    lambdas = [float(m["eigenvalue"]) for m in modes]
    K = ref["K"]
    for lam, mode in zip(lambdas, modes):
        rq = rayleigh_quotient(mesh, mode["coefficients"], K=K, M=M)
        denom = max(abs(lam), 1.0)
        if abs(rq - lam) / denom > RAYLEIGH_REL_TOL:
            return False
    return True


def cluster_ids_match_relative_gap_rule(values: Sequence[float]) -> list[int]:
    """Expected cluster_id sequence from documented relative-gap clustering."""
    clusters = cluster_eigenvalues(values, tol=CLUSTER_REL_GAP_TOL)
    out = [0] * len(values)
    for cid, members in enumerate(clusters):
        for idx in members:
            out[idx] = cid
    return out
