"""Polarity correction, peak location, gate integration, and frame quality.

See ``docs/waveform.md``. One call reduces one frame; pedestal frames use
the fixed gate, pulser frames use the located gate and the quality tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pmwio.constants import (
    GATE_WIDTH,
    INTEGRATION_HALF_WIDTH,
    KIND_PEDESTAL,
    PRE_TRIGGER,
)
from pretrig.robust import BaselineResult, estimate_baseline
from qualitygate.quality import has_pileup, is_saturated, meets_coverage

STATUS_OK = "ok"
STATUS_SATURATED = "saturated"
STATUS_COVERAGE = "coverage"
STATUS_PILEUP = "pileup"


@dataclass(frozen=True)
class FrameReduction:
    """Outcome of reducing one frame."""

    status: str
    charge: float
    charge_var: float
    coverage: float
    n_actual: int
    peak_index: int
    baseline: BaselineResult


def correct(samples: Sequence[int], baseline: float, polarity: int) -> list[float]:
    """Baseline-subtracted trace."""
    _ = polarity
    return [float(sample) - baseline for sample in samples]


def locate_peak(corrected: Sequence[float]) -> int:
    """Index of the largest corrected excursion after the trigger; ties go low."""
    best = PRE_TRIGGER
    for index in range(PRE_TRIGGER + 1, len(corrected)):
        if corrected[index] > corrected[best]:
            best = index
    return best


def reduce_frame(
    samples: Sequence[int],
    *,
    kind: int,
    polarity: int,
    adc_bits: int,
) -> FrameReduction:
    """Estimate the baseline, integrate the gate, and apply the quality tests."""
    if is_saturated(samples, adc_bits):
        return FrameReduction(
            status=STATUS_SATURATED,
            charge=0.0,
            charge_var=0.0,
            coverage=0.0,
            n_actual=0,
            peak_index=-1,
            baseline=estimate_baseline(samples),
        )

    base = estimate_baseline(samples)
    corrected = correct(samples, base.baseline, polarity)

    if kind == KIND_PEDESTAL:
        peak_index = PRE_TRIGGER + INTEGRATION_HALF_WIDTH
        low = PRE_TRIGGER
        high = PRE_TRIGGER + 2 * INTEGRATION_HALF_WIDTH
    else:
        peak_index = locate_peak(corrected)
        low = max(0, peak_index - INTEGRATION_HALF_WIDTH)
        high = min(len(corrected) - 1, peak_index + INTEGRATION_HALF_WIDTH)

    n_actual = high - low + 1
    charge = sum(corrected[low : high + 1])
    coverage = n_actual / GATE_WIDTH
    charge_var = GATE_WIDTH * base.noise_var + GATE_WIDTH * GATE_WIDTH * base.baseline_var

    status = STATUS_OK
    if kind != KIND_PEDESTAL:
        if not meets_coverage(coverage):
            status = STATUS_COVERAGE
        elif has_pileup(corrected, peak_index):
            status = STATUS_PILEUP

    return FrameReduction(
        status=status,
        charge=charge,
        charge_var=charge_var,
        coverage=coverage,
        n_actual=n_actual,
        peak_index=peak_index,
        baseline=base,
    )
