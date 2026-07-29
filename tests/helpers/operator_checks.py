"""Independent operator and eigenspace checks for verifier cases."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def cluster_eigenvalues(values: Sequence[float], tol: float = 1e-7) -> list[list[int]]:
    idx = sorted(range(len(values)), key=lambda i: values[i])
    clusters: list[list[int]] = []
    cur: list[int] = []
    prev = None
    for i in idx:
        if prev is None or abs(values[i] - prev) <= tol:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
        prev = values[i]
    if cur:
        clusters.append(cur)
    return clusters


def principal_angles(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    qa, _ = np.linalg.qr(A)
    qb, _ = np.linalg.qr(B)
    s = np.linalg.svd(qa.T @ qb, compute_uv=False)
    s = np.clip(s, -1.0, 1.0)
    return np.arccos(s)


def subspace_equivalent(A: np.ndarray, B: np.ndarray, angle_tol: float = 0.05) -> bool:
    if A.shape != B.shape:
        return False
    angles = principal_angles(A, B)
    return bool(np.all(angles <= angle_tol))


def compare_clustered_spectra(
    vals_a: Sequence[float],
    vecs_a: Sequence[Sequence[float]],
    vals_b: Sequence[float],
    vecs_b: Sequence[Sequence[float]],
    *,
    val_tol: float = 1e-6,
    angle_tol: float = 0.05,
) -> bool:
    if len(vals_a) != len(vals_b):
        return False
    ca = cluster_eigenvalues(vals_a, val_tol)
    cb = cluster_eigenvalues(vals_b, val_tol)
    if len(ca) != len(cb):
        return False
    for ga, gb in zip(ca, cb):
        if abs(np.mean([vals_a[i] for i in ga]) - np.mean([vals_b[i] for i in gb])) > val_tol:
            return False
        A = np.column_stack([vecs_a[i] for i in ga])
        B = np.column_stack([vecs_b[i] for i in gb])
        if not subspace_equivalent(A, B, angle_tol=angle_tol):
            return False
    return True


def generalized_residual(K: np.ndarray, M: np.ndarray, lam: float, x: np.ndarray) -> float:
    r = K @ x - lam * (M @ x)
    return float(np.linalg.norm(r) / max(1.0, np.linalg.norm(x)))
