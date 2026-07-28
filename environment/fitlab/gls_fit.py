"""Per-lane generalized least squares gain, drift, and intercept fit.

See ``docs/gls_calibration.md``. The covariance carries a common-mode block for every
group of observations that froze the same pedestal epoch, so an ordinary
weighted fit does not reproduce these numbers.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from pmwio.constants import (
    COMMON_MODE_SCALE,
    COND_THRESHOLD,
    MIN_DISTINCT_LEVELS,
    MIN_OBS,
)

STATUS_OK = "ok"
STATUS_NOISY = "noisy"
STATUS_INSUFFICIENT = "insufficient"
STATUS_SINGULAR = "singular"

_PARAMETERS = 3


@dataclass(frozen=True)
class Observation:
    """One accepted pulser observation of one lane."""

    level: int
    time_s: float
    charge: float
    variance: float
    epoch: int


@dataclass(frozen=True)
class FitResult:
    """Fitted parameters and diagnostics for one lane."""

    status: str
    n_obs: int
    distinct_levels: int
    intercept: float
    intercept_sigma: float
    gain: float
    gain_sigma: float
    gain_var: float
    drift: float
    drift_sigma: float
    t0: float
    chi2: float
    dof: int
    chi2_per_dof: float | None
    cond: float


def _unfitted(status: str, n_obs: int, distinct_levels: int) -> FitResult:
    return FitResult(
        status=status,
        n_obs=n_obs,
        distinct_levels=distinct_levels,
        intercept=0.0,
        intercept_sigma=0.0,
        gain=0.0,
        gain_sigma=0.0,
        gain_var=0.0,
        drift=0.0,
        drift_sigma=0.0,
        t0=0.0,
        chi2=0.0,
        dof=0,
        chi2_per_dof=None,
        cond=0.0,
    )


def build_covariance(observations: Sequence[Observation]) -> np.ndarray:
    """Diagonal observation variances plus the shared-pedestal common mode."""
    count = len(observations)
    covariance = np.zeros((count, count), dtype=np.float64)
    diagonal = np.array([obs.variance for obs in observations], dtype=np.float64)
    np.fill_diagonal(covariance, diagonal)

    groups: dict[int, list[int]] = {}
    for index, obs in enumerate(observations):
        groups.setdefault(obs.epoch, []).append(index)

    for members in groups.values():
        if len(members) < 2:
            continue
        common = COMMON_MODE_SCALE * float(np.mean(diagonal[members]))
        for position, row in enumerate(members):
            for column in members[position + 1 :]:
                covariance[row, column] += common
                covariance[column, row] += common
    return covariance


def fit_lane(
    observations: Sequence[Observation],
    *,
    noisy_rejections: int,
) -> FitResult:
    """Solve one lane's GLS fit and classify the outcome."""
    count = len(observations)
    distinct_levels = len({obs.level for obs in observations})

    if count < MIN_OBS and noisy_rejections > 0:
        return _unfitted(STATUS_NOISY, count, distinct_levels)
    if count < MIN_OBS or distinct_levels < MIN_DISTINCT_LEVELS:
        return _unfitted(STATUS_INSUFFICIENT, count, distinct_levels)

    times = np.array([obs.time_s for obs in observations], dtype=np.float64)
    t0 = float(times.mean())
    design = np.column_stack(
        (
            np.ones(count, dtype=np.float64),
            np.array([float(obs.level) for obs in observations], dtype=np.float64),
            times - t0,
        )
    )
    charges = np.array([obs.charge for obs in observations], dtype=np.float64)
    covariance = build_covariance(observations)

    try:
        raw_normal = design.T @ design
        raw_cond = float(
            np.linalg.norm(raw_normal, 1)
            * np.linalg.norm(np.linalg.pinv(raw_normal), 1)
        )
        if not math.isfinite(raw_cond) or raw_cond > COND_THRESHOLD:
            return _unfitted(STATUS_SINGULAR, count, distinct_levels)

        factor = np.linalg.cholesky(covariance)
        whitened_charges = np.linalg.solve(factor, charges)
        normal = design.T @ design
        parameter_cov = np.linalg.inv(normal)
        beta = np.linalg.solve(normal, design.T @ whitened_charges)
    except np.linalg.LinAlgError:
        return _unfitted(STATUS_SINGULAR, count, distinct_levels)

    cond = float(np.linalg.norm(normal, 1) * np.linalg.norm(parameter_cov, 1))
    if not math.isfinite(cond) or cond > COND_THRESHOLD:
        return _unfitted(STATUS_SINGULAR, count, distinct_levels)

    residual = charges - design @ beta
    chi2 = float(residual @ residual)
    dof = count - 1
    variances = [float(parameter_cov[index, index]) for index in range(_PARAMETERS)]
    sigmas = [math.sqrt(value) if value > 0.0 else 0.0 for value in variances]

    return FitResult(
        status=STATUS_OK,
        n_obs=count,
        distinct_levels=distinct_levels,
        intercept=float(beta[0]),
        intercept_sigma=sigmas[0],
        gain=float(beta[1]),
        gain_sigma=sigmas[1],
        gain_var=variances[1],
        drift=float(beta[2]),
        drift_sigma=sigmas[2],
        t0=t0,
        chi2=chi2,
        dof=dof,
        chi2_per_dof=chi2 / dof if dof > 0 else None,
        cond=cond,
    )
