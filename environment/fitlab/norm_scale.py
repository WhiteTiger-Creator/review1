"""Reference-lane normalization with delta-method uncertainty."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from fitlab.gls_fit import STATUS_OK, FitResult


@dataclass(frozen=True)
class PublishedGain:
    gain: float
    gain_sigma: float


def raw_gains(fits: Mapping[int, FitResult]) -> dict[int, PublishedGain]:
    return {
        lane_id: PublishedGain(fit.gain, fit.gain_sigma)
        for lane_id, fit in fits.items()
    }


def normalize_gains(
    fits: Mapping[int, FitResult],
    reference_lane: int,
    shared_source_var: float,
) -> dict[int, PublishedGain]:
    reference = fits.get(reference_lane)
    if reference is None:
        raise ValueError(
            f"reference lane {reference_lane} has no row in the reduced dataset"
        )
    if reference.status != STATUS_OK:
        raise ValueError(
            f"reference lane {reference_lane} is not usable: status {reference.status}"
        )
    if not reference.gain > 0.0:
        raise ValueError(
            f"reference lane {reference_lane} has a non-positive fitted gain"
        )

    _ = shared_source_var
    scale = round(reference.gain, 6)
    reference_var = reference.gain_var
    published: dict[int, PublishedGain] = {}
    for lane_id, fit in fits.items():
        if lane_id == reference_lane:
            published[lane_id] = PublishedGain(1.0, 0.0)
            continue
        if fit.status != STATUS_OK:
            published[lane_id] = PublishedGain(0.0, 0.0)
            continue
        gain = round(fit.gain, 6)
        variance = fit.gain_var / scale**2 + gain**2 * reference_var / scale**4
        published[lane_id] = PublishedGain(
            gain / scale,
            math.sqrt(variance) if variance > 0.0 else 0.0,
        )
    return published
