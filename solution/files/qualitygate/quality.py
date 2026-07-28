"""Frame-quality predicates.

See ``docs/waveform.md``, section *Frame-quality tests*. The tests are
pure predicates here; the order in which they are applied, and the counter each
failure feeds, live in the reduction driver.
"""

from __future__ import annotations

from collections.abc import Sequence

from pmwio.constants import MIN_COVERAGE, PILEUP_FRAC, PILEUP_SEP, PRE_TRIGGER
from pmwio.decoder import adc_rails


def is_saturated(samples: Sequence[int], adc_bits: int) -> bool:
    """True when any raw sample touches either digitizer rail."""
    rail_low, rail_high = adc_rails(adc_bits)
    return any(sample >= rail_high or sample <= rail_low for sample in samples)


def meets_coverage(coverage: float) -> bool:
    """True when a clipped gate still carries enough of the nominal window."""
    return coverage >= MIN_COVERAGE


def secondary_amplitude(corrected: Sequence[float], peak_index: int) -> float | None:
    """Largest corrected excursion further than ``PILEUP_SEP`` from the peak."""
    candidates = [
        corrected[index]
        for index in range(PRE_TRIGGER, len(corrected))
        if abs(index - peak_index) > PILEUP_SEP
    ]
    if not candidates:
        return None
    return max(candidates)


def has_pileup(corrected: Sequence[float], peak_index: int) -> bool:
    """True when a second pulse rides far enough from the primary to matter."""
    secondary = secondary_amplitude(corrected, peak_index)
    if secondary is None:
        return False
    return secondary > 0.0 and secondary >= PILEUP_FRAC * corrected[peak_index]
