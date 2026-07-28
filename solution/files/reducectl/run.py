"""Offline calibration session driver.

Reads a profile from ``runbook/campaign.toml``, decodes and merges its shards,
reduces every frame in documented process order, fits each lane, normalizes if
the profile asks for it, and publishes both artifacts atomically. The stage
contracts live under ``docs/``; this module only sequences them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib
from artiforge.atomic import write_artifacts
from artiforge.digest import publish_float, seal
from chargegate.charge import (
    STATUS_COVERAGE,
    STATUS_PILEUP,
    STATUS_SATURATED,
    reduce_frame,
)
from coalesce.merge import merge_shards, validate_shard_set
from fitlab.gls_fit import STATUS_OK, FitResult, Observation, fit_lane
from fitlab.norm_scale import PublishedGain, normalize_gains, raw_gains
from pedtrack.rolling import (
    ADMIT_NO_PEDESTAL,
    ADMIT_NOISY,
    PedestalTracker,
    admit,
    pedestal_correct,
)
from pmwio.constants import KIND_PEDESTAL, SCHEMA_VERSION
from pmwio.decoder import WaveFrame, decode_shard

NANOSECONDS_PER_SECOND = 1e9


@dataclass(frozen=True)
class ProfileConfig:
    """One profile section of ``runbook/campaign.toml``."""

    name: str
    shards: tuple[str, ...]
    reference_lane: int | None
    shared_source_var: float


@dataclass
class Reduction:
    """Everything the frame pass produces."""

    tracker: PedestalTracker
    lane_ids: set[int] = field(default_factory=set)
    observations: dict[int, list[Observation]] = field(default_factory=dict)
    noisy_by_lane: dict[int, int] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)


def load_profile(root: Path, name: str) -> ProfileConfig:
    """Read one profile declaration from disk."""
    path = root / "runbook" / "campaign.toml"
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except OSError as err:
        raise ValueError(f"cannot read profile table {path}: {err}") from err

    sections = {
        key: value for key, value in document.items() if isinstance(value, dict)
    }
    if name not in sections:
        raise ValueError(f"unknown profile {name}")
    section = sections[name]

    declared = section.get("shards")
    shards = (
        tuple(str(item) for item in declared) if isinstance(declared, list) else ()
    )
    if not shards:
        raise ValueError(f"profile has no acquisition shards: {name}")

    reference_lane = None
    if "reference_lane" in section:
        try:
            reference_lane = int(section["reference_lane"])
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"profile {name} declares an unusable reference lane"
            ) from err

    try:
        shared_source_var = float(section.get("shared_source_var", 0.0))
    except (TypeError, ValueError) as err:
        raise ValueError(
            f"profile {name} declares an invalid shared_source_var"
        ) from err

    return ProfileConfig(
        name=name,
        shards=shards,
        reference_lane=reference_lane,
        shared_source_var=shared_source_var,
    )


def _reduce_frames(frames: list[WaveFrame]) -> Reduction:
    """Walk the merged frames once, in documented process order."""
    reduction = Reduction(tracker=PedestalTracker())
    counters = dict.fromkeys(
        (
            "pedestal_frames",
            "frames_rejected_saturation",
            "frames_rejected_coverage",
            "frames_rejected_pileup",
            "frames_rejected_no_pedestal",
            "frames_rejected_noisy",
            "frames_accepted",
        ),
        0,
    )

    for frame in frames:
        reduction.lane_ids.add(frame.lane_id)
        result = reduce_frame(
            frame.samples,
            kind=frame.kind,
            polarity=frame.polarity,
            adc_bits=frame.adc_bits,
        )
        if result.status == STATUS_SATURATED:
            counters["frames_rejected_saturation"] += 1
            continue
        if frame.kind == KIND_PEDESTAL:
            reduction.tracker.record(frame.lane_id, result.charge)
            counters["pedestal_frames"] += 1
            continue
        if result.status == STATUS_COVERAGE:
            counters["frames_rejected_coverage"] += 1
            continue
        if result.status == STATUS_PILEUP:
            counters["frames_rejected_pileup"] += 1
            continue

        state = reduction.tracker.state(frame.lane_id)
        decision = admit(state)
        if decision == ADMIT_NO_PEDESTAL:
            counters["frames_rejected_no_pedestal"] += 1
            continue
        if decision == ADMIT_NOISY:
            counters["frames_rejected_noisy"] += 1
            reduction.noisy_by_lane[frame.lane_id] = (
                reduction.noisy_by_lane.get(frame.lane_id, 0) + 1
            )
            continue

        charge, pedestal_var = pedestal_correct(result.charge, result.coverage, state)
        reduction.observations.setdefault(frame.lane_id, []).append(
            Observation(
                level=frame.pulser_level,
                time_s=frame.timestamp_ns / NANOSECONDS_PER_SECOND,
                charge=charge,
                variance=result.charge_var + pedestal_var,
                epoch=state.epoch,
            )
        )
        counters["frames_accepted"] += 1

    reduction.counters = counters
    return reduction


def _lane_row(
    lane_id: int,
    fit: FitResult,
    published: PublishedGain,
    pedestal_charge: float,
    pedestal_sigma: float,
) -> dict[str, Any]:
    chi2_per_dof = fit.chi2_per_dof
    return {
        "lane_id": lane_id,
        "status": fit.status,
        "n_obs": fit.n_obs,
        "distinct_levels": fit.distinct_levels,
        "pedestal_charge": publish_float(pedestal_charge),
        "pedestal_sigma": publish_float(pedestal_sigma),
        "gain": publish_float(published.gain),
        "gain_sigma": publish_float(published.gain_sigma),
        "intercept": publish_float(fit.intercept),
        "intercept_sigma": publish_float(fit.intercept_sigma),
        "drift": publish_float(fit.drift),
        "drift_sigma": publish_float(fit.drift_sigma),
        "t0": publish_float(fit.t0),
        "chi2": publish_float(fit.chi2),
        "dof": fit.dof,
        "chi2_per_dof": None if chi2_per_dof is None else publish_float(chi2_per_dof),
        "cond": publish_float(fit.cond),
    }


def reduce_calibration(
    root: Path,
    profile_name: str,
    report_path: Path,
    state_path: Path,
) -> dict[str, Any]:
    """Run one calibration profile end to end and publish both artifacts."""
    config = load_profile(root, profile_name)
    fixtures = root / "fixtures"
    shards = [decode_shard(fixtures / basename) for basename in config.shards]
    run_id, adc_bits = validate_shard_set(shards)

    frames, merge_stats = merge_shards(shards)
    reduction = _reduce_frames(frames)

    fits = {
        lane_id: fit_lane(
            reduction.observations.get(lane_id, []),
            noisy_rejections=reduction.noisy_by_lane.get(lane_id, 0),
        )
        for lane_id in sorted(reduction.lane_ids)
    }
    if config.reference_lane is None:
        published = raw_gains(fits)
    else:
        published = normalize_gains(
            fits, config.reference_lane, config.shared_source_var
        )

    lanes = []
    for lane_id, fit in fits.items():
        state = reduction.tracker.state(lane_id)
        lanes.append(
            _lane_row(lane_id, fit, published[lane_id], state.charge, state.sigma)
        )
    lanes_fitted = sum(1 for fit in fits.values() if fit.status == STATUS_OK)

    counters = reduction.counters
    provenance = {
        "frames_read": merge_stats.frames_read,
        "frames_rejected_duplicate": merge_stats.frames_rejected_duplicate,
        "frames_conflicting": merge_stats.frames_conflicting,
        "pedestal_frames": counters["pedestal_frames"],
        "frames_rejected_saturation": counters["frames_rejected_saturation"],
        "frames_rejected_coverage": counters["frames_rejected_coverage"],
        "frames_rejected_pileup": counters["frames_rejected_pileup"],
        "frames_rejected_no_pedestal": counters["frames_rejected_no_pedestal"],
        "frames_rejected_noisy": counters["frames_rejected_noisy"],
        "frames_accepted": counters["frames_accepted"],
        "lanes_fitted": lanes_fitted,
        "lanes_rejected": len(fits) - lanes_fitted,
    }

    report = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "profile": config.name,
            "run_id": run_id,
            "adc_bits": adc_bits,
            "reference_lane": config.reference_lane,
            "normalized": config.reference_lane is not None,
            "input_shards": sorted(shard.basename for shard in shards),
            "provenance": provenance,
            "lanes": lanes,
        },
        "calibration_digest",
    )
    state = seal(
        {
            "schema_version": SCHEMA_VERSION,
            "last_profile": config.name,
            "last_run_id": run_id,
            "adc_bits": adc_bits,
            "lane_count": len(lanes),
            "lanes_fitted": lanes_fitted,
            "calibration_digest": report["calibration_digest"],
        },
        "replay_fingerprint",
    )

    write_artifacts(report_path, report, state_path, state)
    return report
