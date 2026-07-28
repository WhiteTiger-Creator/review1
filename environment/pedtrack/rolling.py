"""Per-lane rolling pedestal population.

See ``docs/rolling_pedestal.md``. Frames are visited once, in documented process
order; an observation freezes the pedestal state that was current at its process
time and never revisits it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from pmwio.constants import (
    MAD_SCALE,
    NOISE_SIGMA_LIMIT,
    PEDESTAL_K,
    PEDESTAL_P,
    PEDESTAL_VAR_FLOOR,
)
from pretrig.robust import median, median_absolute_deviation

ADMIT_OK = "ok"
ADMIT_NO_PEDESTAL = "no_pedestal"
ADMIT_NOISY = "noisy"


@dataclass(frozen=True)
class PedestalState:
    """Robust summary of one lane's rolling window at a point in time."""

    charge: float
    variance: float
    sigma: float
    epoch: int
    size: int


class PedestalTracker:
    """Rolling pedestal windows for every lane seen so far."""

    def __init__(self) -> None:
        self._windows: dict[int, deque[float]] = {}
        self._epochs: dict[int, int] = {}

    def record(self, lane_id: int, charge: float) -> None:
        """Append a reduced pedestal charge and advance the lane's epoch."""
        window = self._windows.get(lane_id)
        if window is None:
            window = deque(maxlen=PEDESTAL_K)
            self._windows[lane_id] = window
        window.append(charge)
        self._epochs[lane_id] = self._epochs.get(lane_id, 0) + 1

    def state(self, lane_id: int) -> PedestalState:
        """Window statistics for ``lane_id`` as of now."""
        window = list(self._windows.get(lane_id, ()))
        epoch = self._epochs.get(lane_id, 0)
        if not window:
            return PedestalState(
                charge=0.0,
                variance=PEDESTAL_VAR_FLOOR,
                sigma=0.0,
                epoch=epoch,
                size=0,
            )
        location = median(window)
        sigma = MAD_SCALE * median_absolute_deviation(window, location)
        return PedestalState(
            charge=location,
            variance=max(sigma * sigma, PEDESTAL_VAR_FLOOR),
            sigma=sigma,
            epoch=epoch,
            size=len(window),
        )

    def lanes(self) -> list[int]:
        """Lanes that have contributed at least one reduced pedestal frame."""
        return sorted(self._windows)


def admit(state: PedestalState) -> str:
    """Decide whether a reduced pulser frame may become an observation."""
    if state.size < PEDESTAL_P:
        return ADMIT_NO_PEDESTAL
    if state.sigma > NOISE_SIGMA_LIMIT:
        return ADMIT_NOISY
    return ADMIT_OK


def pedestal_correct(
    charge: float,
    coverage: float,
    state: PedestalState,
) -> tuple[float, float]:
    """Subtract the coverage-scaled pedestal and return ``(q, p_var)``."""
    return charge - coverage * state.charge, coverage * coverage * state.variance
