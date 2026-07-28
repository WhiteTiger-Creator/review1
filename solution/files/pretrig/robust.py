"""Two-pass robust baseline estimation.

See ``docs/waveform.md``, section *Two-pass robust baseline*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pmwio.constants import (
    MAD_SCALE,
    MEDIAN_VARIANCE_FACTOR,
    MIN_BASELINE_SAMPLES,
    OUTLIER_K,
    PRE_TRIGGER,
    QUANTIZATION_VAR,
)


@dataclass(frozen=True)
class BaselineResult:
    """Baseline location, scale, and the variances derived from them."""

    baseline: float
    sigma: float
    noise_var: float
    baseline_var: float
    n_base: int


def median(values: Sequence[float]) -> float:
    """Population median; the mean of the two central values on even lengths."""
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def median_absolute_deviation(values: Sequence[float], center: float) -> float:
    """Median of ``|value - center|`` over ``values``."""
    return median([abs(value - center) for value in values])


def estimate_baseline(samples: Sequence[int]) -> BaselineResult:
    """Estimate the baseline from the pre-trigger region of one frame."""
    window = [float(sample) for sample in samples[:PRE_TRIGGER]]
    first = median(window)
    sigma_first = MAD_SCALE * median_absolute_deviation(window, first)

    if sigma_first == 0.0:
        retained = window
    else:
        cut = OUTLIER_K * sigma_first
        retained = [value for value in window if abs(value - first) <= cut]

    if len(retained) < MIN_BASELINE_SAMPLES:
        baseline = first
        sigma = sigma_first
        n_base = len(window)
    else:
        baseline = median(retained)
        sigma = MAD_SCALE * median_absolute_deviation(retained, baseline)
        n_base = len(retained)

    noise_var = max(sigma * sigma, QUANTIZATION_VAR)
    baseline_var = MEDIAN_VARIANCE_FACTOR * noise_var / n_base if n_base else 0.0
    return BaselineResult(
        baseline=baseline,
        sigma=sigma,
        noise_var=noise_var,
        baseline_var=baseline_var,
        n_base=n_base,
    )
