"""Independent reference for repeated-subspace canonical basis (Section 4a)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from helpers.mode_payload_checks import (
    COEFF_TOL,
    M_ORTHONORM_TOL,
    RAYLEIGH_REL_TOL,
    REPEATED_SUBGROUP_TOL,
    cluster_ids_match_relative_gap_rule,
    first_significant_coeff_positive,
    rayleigh_quotient,
)
from scipy.sparse import csr_matrix

PROBE_NORM_TOL = 1e-12


def m_inner(a: np.ndarray, b: np.ndarray, M: csr_matrix) -> float:
    return float(a @ (M @ b))


def m_norm(v: np.ndarray, M: csr_matrix) -> float:
    return float(np.sqrt(max(0.0, m_inner(v, v, M))))


def _relative_gap(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0)


def repeated_subgroups_in_cluster(
    values: Sequence[float],
    cluster_ids: Sequence[int],
    cid: int,
) -> list[list[int]]:
    members = sorted([i for i, c in enumerate(cluster_ids) if c == cid], key=lambda i: values[i])
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


def project_coordinate(V: np.ndarray, M: csr_matrix, r: int) -> np.ndarray:
    n = V.shape[0]
    er = np.zeros(n, dtype=np.float64)
    er[r] = 1.0
    coeffs = V.T @ (M @ er)
    return V @ coeffs


def mgs_two_pass(w: np.ndarray, M: csr_matrix, accepted: list[np.ndarray]) -> np.ndarray:
    out = w.copy()
    for _ in range(2):
        for q in accepted:
            out = out - m_inner(q, out, M) * q
    return out


def fix_sign(v: np.ndarray) -> np.ndarray:
    out = v.copy()
    for c in out:
        if abs(float(c)) > PROBE_NORM_TOL:
            if float(c) < 0.0:
                out *= -1.0
            break
    return out


def canonicalize_repeated_subgroup(
    K: csr_matrix,
    M: csr_matrix,
    values: list[float],
    vectors: list[np.ndarray],
    indices: list[int],
) -> None:
    k = len(indices)
    if k <= 1:
        return
    V = np.column_stack([vectors[i] for i in indices])
    n = V.shape[0]
    accepted: list[np.ndarray] = []
    for r in range(n):
        if len(accepted) >= k:
            break
        w = project_coordinate(V, M, r)
        w = mgs_two_pass(w, M, accepted)
        norm = m_norm(w, M)
        if norm <= PROBE_NORM_TOL:
            continue
        w = fix_sign(w / norm)
        accepted.append(w)
    if len(accepted) != k:
        raise ValueError("cannot construct canonical repeated-subspace basis")
    for j, idx in enumerate(indices):
        vectors[idx] = accepted[j]
        values[idx] = rayleigh_quotient(None, accepted[j], K=K, M=M)


def canonicalize_mode_set(
    K: csr_matrix,
    M: csr_matrix,
    values: Sequence[float],
    vectors: Sequence[np.ndarray],
) -> tuple[list[float], list[np.ndarray]]:
    vals = [float(v) for v in values]
    vecs = [np.asarray(v, dtype=np.float64).copy() for v in vectors]
    for i, v in enumerate(vecs):
        n = m_norm(v, M)
        if n > 1e-30:
            vecs[i] = v / n

    cluster_ids = cluster_ids_match_relative_gap_rule(vals)
    for cid in sorted(set(cluster_ids)):
        for group in repeated_subgroups_in_cluster(vals, cluster_ids, cid):
            if len(group) > 1:
                canonicalize_repeated_subgroup(K, M, vals, vecs, group)

    for i, v in enumerate(vecs):
        vecs[i] = fix_sign(v)
        vals[i] = rayleigh_quotient(None, vecs[i], K=K, M=M)

    order = sorted(range(len(vals)), key=lambda i: vals[i])
    vals = [vals[i] for i in order]
    vecs = [vecs[i] for i in order]
    return vals, vecs


def payloads_match_canonical_contract(
    a_modes: Sequence[dict],
    b_modes: Sequence[dict],
    M: csr_matrix,
    K: csr_matrix,
) -> bool:
    """Elementwise coefficient agreement plus sign and orthonormality checks."""
    if len(a_modes) != len(b_modes):
        return False
    vals_a = [float(m["eigenvalue"]) for m in a_modes]
    vals_b = [float(m["eigenvalue"]) for m in b_modes]
    if not np.allclose(vals_a, vals_b, rtol=RAYLEIGH_REL_TOL, atol=0.0):
        return False
    cids_a = [int(m["cluster_id"]) for m in a_modes]
    cids_b = [int(m["cluster_id"]) for m in b_modes]
    if cids_a != cids_b:
        return False
    for ma, mb in zip(a_modes, b_modes):
        ca = np.asarray(ma["coefficients"], dtype=np.float64)
        cb = np.asarray(mb["coefficients"], dtype=np.float64)
        if np.max(np.abs(ca - cb)) > COEFF_TOL:
            return False
        if not first_significant_coeff_positive(ca):
            return False
        if not first_significant_coeff_positive(cb):
            return False
    vecs = np.column_stack([np.asarray(m["coefficients"], dtype=np.float64) for m in a_modes])
    gram = vecs.T @ (M @ vecs)
    if np.max(np.abs(gram - np.eye(len(a_modes)))) > M_ORTHONORM_TOL:
        return False
    for lam, mode in zip(vals_a, a_modes):
        rq = rayleigh_quotient(None, mode["coefficients"], K=K, M=M)
        if abs(rq - lam) / max(abs(lam), 1.0) > RAYLEIGH_REL_TOL:
            return False
    return True
