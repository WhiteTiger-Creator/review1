#!/usr/bin/env bash
# Install the corrected offline PMW2 reduction modules, then replay all profiles.
set -euo pipefail
cd /app/environment

cat > artiforge/atomic.py <<'ORACLE_ARTIFORGE_ATOMIC_PY'
"""Transactional artifact writes.

See ``docs/artifacts.md``, section *Atomic, transactional writes*. Both
artifacts are rendered and validated before either destination is touched, so a
run writes both or neither.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def render(payload: Any) -> bytes:
    """Render one artifact exactly as it is stored on disk."""
    text = json.dumps(payload, indent=2, allow_nan=False, ensure_ascii=True)
    return (text + "\n").encode("utf-8")


def _stage(path: Path, blob: bytes) -> Path:
    """Write ``blob`` to a durable temporary file beside ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    staged = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        staged.unlink(missing_ok=True)
        raise
    return staged


def write_artifacts(
    report_path: Path,
    report: Any,
    state_path: Path,
    state: Any,
) -> None:
    """Write the calibration report and the replay state atomically."""
    report_blob = render(report)
    state_blob = render(state)

    staged_report = _stage(report_path, report_blob)
    try:
        staged_state = _stage(state_path, state_blob)
    except OSError:
        staged_report.unlink(missing_ok=True)
        raise

    try:
        staged_report.replace(report_path)
        staged_state.replace(state_path)
    except OSError:
        staged_report.unlink(missing_ok=True)
        staged_state.unlink(missing_ok=True)
        raise
ORACLE_ARTIFORGE_ATOMIC_PY

cat > artiforge/digest.py <<'ORACLE_ARTIFORGE_DIGEST_PY'
"""Documented JSON encoding, publication rounding, and digest bindings.

See ``docs/artifacts.md``, sections *Rounding*, *Documented encoding*, and
*Digest bindings*.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pmwio.constants import PUBLICATION_DIGITS


def compact_bytes(payload: Any) -> bytes:
    """Serialize ``payload`` to the documented encoding both digests hash."""
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    )
    return text.encode("utf-8")


def content_digest(payload: Any) -> str:
    """Lowercase hex SHA-256 of the documented encoding of ``payload``."""
    return hashlib.sha256(compact_bytes(payload)).hexdigest()


def seal(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Store the digest of ``payload`` without ``key`` into ``payload[key]``."""
    body = {name: value for name, value in payload.items() if name != key}
    payload[key] = content_digest(body)
    return payload


def publish_float(value: float) -> float:
    """Round one published float, mapping a rounded ``-0.0`` onto ``0.0``."""
    rounded = round(float(value), PUBLICATION_DIGITS)
    return 0.0 if rounded == 0.0 else rounded
ORACLE_ARTIFORGE_DIGEST_PY

cat > chargegate/charge.py <<'ORACLE_CHARGEGATE_CHARGE_PY'
"""Polarity correction, peak location, gate integration, and frame quality.

See ``docs/waveform.md``. One call reduces one frame; pedestal frames use
the fixed gate, pulser frames use the located gate and the quality tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pretrig.robust import BaselineResult, estimate_baseline
from pmwio.constants import (
    GATE_WIDTH,
    INTEGRATION_HALF_WIDTH,
    KIND_PEDESTAL,
    PRE_TRIGGER,
)
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
    """Polarity-corrected trace: a physical pulse is a positive excursion."""
    return [polarity * (float(sample) - baseline) for sample in samples]


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
    charge_var = n_actual * base.noise_var + n_actual * n_actual * base.baseline_var

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
ORACLE_CHARGEGATE_CHARGE_PY

cat > coalesce/merge.py <<'ORACLE_COALESCE_MERGE_PY'
"""Shard-set consistency and acquisition-identity merge.

See ``docs/container.md``, sections *Shard-set consistency* and *Merge*.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pmwio.decoder import ShardRecord, WaveFrame


@dataclass(frozen=True)
class MergeStats:
    """Counters produced by :func:`merge_shards`."""

    frames_read: int
    frames_rejected_duplicate: int
    frames_conflicting: int


def validate_shard_set(shards: Sequence[ShardRecord]) -> tuple[int, int]:
    """Return the ``(run_id, adc_bits)`` shared by every shard of a profile."""
    if not shards:
        raise ValueError("profile has no acquisition shards")
    run_ids = {shard.run_id for shard in shards}
    if len(run_ids) > 1:
        raise ValueError(f"mixed run_id across profile shards: {sorted(run_ids)}")
    adc_bits = {shard.adc_bits for shard in shards}
    if len(adc_bits) > 1:
        raise ValueError(f"mixed adc_bits across profile shards: {sorted(adc_bits)}")
    return run_ids.pop(), adc_bits.pop()


def merge_shards(shards: Sequence[ShardRecord]) -> tuple[list[WaveFrame], MergeStats]:
    """Deduplicate acquisition identities and place survivors in process order.

    Shards are visited by ascending ``(shard_index, basename)``, so the result is
    invariant under permutation of the profile's shard list. Within one shard the
    earlier occurrence of a repeated identity wins.
    """
    retained: dict[tuple[int, int, int], WaveFrame] = {}
    frames_read = 0
    duplicates = 0
    conflicting = 0

    for shard in sorted(shards, key=lambda record: record.priority):
        for frame in shard.frames:
            frames_read += 1
            kept = retained.get(frame.identity)
            if kept is None:
                retained[frame.identity] = frame
                continue
            duplicates += 1
            if kept.content != frame.content:
                conflicting += 1

    def process_order(frame: WaveFrame) -> tuple[int, int, int, int]:
        return (frame.timestamp_ns, frame.kind, frame.lane_id, frame.acq_seq)

    ordered = sorted(retained.values(), key=process_order)
    stats = MergeStats(
        frames_read=frames_read,
        frames_rejected_duplicate=duplicates,
        frames_conflicting=conflicting,
    )
    return ordered, stats
ORACLE_COALESCE_MERGE_PY

cat > fitlab/gls_fit.py <<'ORACLE_FITLAB_GLS_FIT_PY'
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
        # Apply V^{-1} through dense solves rather than forming inv(V).
        weighted_design = np.linalg.solve(covariance, design)
        weighted_charges = np.linalg.solve(covariance, charges)
        normal = design.T @ weighted_design
        parameter_cov = np.linalg.inv(normal)
        beta = np.linalg.solve(normal, design.T @ weighted_charges)
    except np.linalg.LinAlgError:
        return _unfitted(STATUS_SINGULAR, count, distinct_levels)

    cond = float(np.linalg.norm(normal, 1) * np.linalg.norm(parameter_cov, 1))
    if not math.isfinite(cond) or cond > COND_THRESHOLD:
        return _unfitted(STATUS_SINGULAR, count, distinct_levels)

    residual = charges - design @ beta
    chi2 = float(residual @ np.linalg.solve(covariance, residual))
    dof = count - _PARAMETERS
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
ORACLE_FITLAB_GLS_FIT_PY

cat > fitlab/norm_scale.py <<'ORACLE_FITLAB_NORM_SCALE_PY'
"""Reference-lane normalization with delta-method uncertainty.

See ``docs/lane_scale.md``. Normalization is a publication step: it runs on
the fully reduced dataset and changes no provenance counter.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from fitlab.gls_fit import STATUS_OK, FitResult


@dataclass(frozen=True)
class PublishedGain:
    """Gain and sigma as they are published for one lane."""

    gain: float
    gain_sigma: float


def raw_gains(fits: Mapping[int, FitResult]) -> dict[int, PublishedGain]:
    """Publish fitted gains directly, as a profile without a reference lane does."""
    return {
        lane_id: PublishedGain(fit.gain, fit.gain_sigma)
        for lane_id, fit in fits.items()
    }


def normalize_gains(
    fits: Mapping[int, FitResult],
    reference_lane: int,
    shared_source_var: float,
) -> dict[int, PublishedGain]:
    """Convert fitted gains to ratios against the reference lane.

    The reference lane defines the unit of the scale and publishes exactly
    ``1.0 +/- 0.0``. A reference lane that was not fitted fails the whole run.
    """
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

    scale = reference.gain
    reference_var = reference.gain_var
    published: dict[int, PublishedGain] = {}
    for lane_id, fit in fits.items():
        if lane_id == reference_lane:
            published[lane_id] = PublishedGain(1.0, 0.0)
            continue
        if fit.status != STATUS_OK:
            published[lane_id] = PublishedGain(0.0, 0.0)
            continue
        gain = fit.gain
        # q^2 * (var_g/g^2 + var_r/r^2 - 2 cov/(g r)), expanded so that g may vanish.
        variance = (
            fit.gain_var / scale**2
            + gain**2 * reference_var / scale**4
            - 2.0 * gain * shared_source_var / scale**3
        )
        published[lane_id] = PublishedGain(
            gain / scale,
            math.sqrt(variance) if variance > 0.0 else 0.0,
        )
    return published
ORACLE_FITLAB_NORM_SCALE_PY

cat > pmwio/decoder.py <<'ORACLE_PMWIO_DECODER_PY'
"""PMW2 acquisition container codec.

Layout, validation order, and error wording follow ``docs/container.md``.
Decoding is total: a shard either yields exactly ``frame_count`` fully validated
frames and ends at end of file, or it raises :class:`ValueError`.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pmwio.constants import (
    FILE_HEADER_BYTES,
    FRAME_HEADER_BYTES,
    MAX_SAMPLE_COUNT,
    MIN_SAMPLE_COUNT,
    PMW2_MAGIC,
    PMW2_VERSION,
    VALID_ADC_BITS,
    VALID_KINDS,
    VALID_POLARITIES,
)

_FILE_HEADER = struct.Struct("<4sHHIHHII")
_FRAME_HEADER = struct.Struct("<HHIIqHhI")


@dataclass(frozen=True)
class WaveFrame:
    """One acquisition frame with its decoded samples."""

    lane_id: int
    kind: int
    acq_seq: int
    pulser_level: int
    timestamp_ns: int
    sample_count: int
    polarity: int
    samples: tuple[int, ...]
    run_id: int
    adc_bits: int
    source_basename: str
    source_shard_index: int

    @property
    def identity(self) -> tuple[int, int, int]:
        """Acquisition identity ``(run_id, lane_id, acq_seq)``."""
        return (self.run_id, self.lane_id, self.acq_seq)

    @property
    def content(self) -> tuple[int, int, int, int, int, tuple[int, ...]]:
        """Everything outside the identity that two frames may disagree on."""
        return (
            self.kind,
            self.pulser_level,
            self.timestamp_ns,
            self.sample_count,
            self.polarity,
            self.samples,
        )


@dataclass(frozen=True)
class ShardRecord:
    """One decoded PMW2 shard file."""

    path: Path
    basename: str
    run_id: int
    shard_index: int
    adc_bits: int
    byte_length: int
    sha256_hex: str
    frames: tuple[WaveFrame, ...]

    @property
    def priority(self) -> tuple[int, str]:
        """Merge priority key; ascending, basename breaking index ties."""
        return (self.shard_index, self.basename)


def adc_rails(adc_bits: int) -> tuple[int, int]:
    """Return ``(rail_low, rail_high)`` for a digitizer of ``adc_bits`` bits."""
    if adc_bits not in VALID_ADC_BITS:
        raise ValueError(f"unsupported adc_bits {adc_bits}")
    span = 1 << (adc_bits - 1)
    return -span, span - 1


def decode_bytes(data: bytes, basename: str, path: Path | None = None) -> ShardRecord:
    """Decode an in-memory PMW2 shard image."""
    if len(data) < FILE_HEADER_BYTES or data[:4] != PMW2_MAGIC:
        raise ValueError(f"unrecognized PMW2 shard {basename}")
    _, version, header_bytes, run_id, shard_index, adc_bits, frame_count, reserved = (
        _FILE_HEADER.unpack_from(data, 0)
    )
    if version != PMW2_VERSION:
        raise ValueError(f"unsupported PMW2 version {version} in {basename}")
    if header_bytes != FILE_HEADER_BYTES:
        raise ValueError(f"unexpected file header size {header_bytes} in {basename}")
    if adc_bits not in VALID_ADC_BITS:
        raise ValueError(f"unsupported adc_bits {adc_bits} in {basename}")
    if reserved != 0:
        raise ValueError(f"reserved file header field must be zero in {basename}")

    rail_low, rail_high = adc_rails(adc_bits)
    frames: list[WaveFrame] = []
    pos = FILE_HEADER_BYTES
    for _ in range(frame_count):
        frame, pos = _decode_frame(
            data,
            pos,
            basename=basename,
            run_id=run_id,
            shard_index=shard_index,
            adc_bits=adc_bits,
            rails=(rail_low, rail_high),
        )
        frames.append(frame)
    if pos != len(data):
        raise ValueError(f"trailing bytes after final frame in {basename}")

    return ShardRecord(
        path=Path(basename) if path is None else path,
        basename=basename,
        run_id=run_id,
        shard_index=shard_index,
        adc_bits=adc_bits,
        byte_length=len(data),
        sha256_hex=hashlib.sha256(data).hexdigest(),
        frames=tuple(frames),
    )


def _decode_frame(
    data: bytes,
    pos: int,
    *,
    basename: str,
    run_id: int,
    shard_index: int,
    adc_bits: int,
    rails: tuple[int, int],
) -> tuple[WaveFrame, int]:
    if pos + FRAME_HEADER_BYTES > len(data):
        raise ValueError(f"truncated PMW2 frame in {basename}")
    (
        lane_id,
        kind,
        acq_seq,
        pulser_level,
        timestamp_ns,
        sample_count,
        polarity,
        crc32,
    ) = _FRAME_HEADER.unpack_from(data, pos)
    pos += FRAME_HEADER_BYTES

    if not MIN_SAMPLE_COUNT <= sample_count <= MAX_SAMPLE_COUNT:
        raise ValueError(f"sample_count out of range: {sample_count} in {basename}")
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown frame kind {kind} in {basename}")
    if polarity not in VALID_POLARITIES:
        raise ValueError(f"invalid polarity {polarity} in {basename}")

    end = pos + 2 * sample_count
    if end > len(data):
        raise ValueError(f"truncated PMW2 frame in {basename}")
    payload = data[pos:end]
    samples = struct.unpack(f"<{sample_count}h", payload)
    rail_low, rail_high = rails
    if min(samples) < rail_low or max(samples) > rail_high:
        raise ValueError(f"sample out of range for adc_bits {adc_bits} in {basename}")
    if (zlib.crc32(payload) & 0xFFFFFFFF) != crc32:
        raise ValueError(f"sample payload CRC mismatch in {basename}")

    frame = WaveFrame(
        lane_id=lane_id,
        kind=kind,
        acq_seq=acq_seq,
        pulser_level=pulser_level,
        timestamp_ns=timestamp_ns,
        sample_count=sample_count,
        polarity=polarity,
        samples=samples,
        run_id=run_id,
        adc_bits=adc_bits,
        source_basename=basename,
        source_shard_index=shard_index,
    )
    return frame, end


def decode_shard(path: Path | str) -> ShardRecord:
    """Read and decode one PMW2 shard file."""
    shard_path = Path(path)
    try:
        data = shard_path.read_bytes()
    except OSError as err:
        raise ValueError(f"missing shard {shard_path.name}: {err}") from err
    return decode_bytes(data, basename=shard_path.name, path=shard_path)


def encode_frame(
    *,
    lane_id: int,
    kind: int,
    acq_seq: int,
    pulser_level: int,
    timestamp_ns: int,
    polarity: int,
    samples: Sequence[int],
) -> bytes:
    """Serialize one frame header and its sample payload."""
    payload = struct.pack(f"<{len(samples)}h", *samples)
    header = _FRAME_HEADER.pack(
        lane_id,
        kind,
        acq_seq,
        pulser_level,
        timestamp_ns,
        len(samples),
        polarity,
        zlib.crc32(payload) & 0xFFFFFFFF,
    )
    return header + payload


def encode_shard(
    *,
    run_id: int,
    shard_index: int,
    adc_bits: int,
    frames: Sequence[bytes],
) -> bytes:
    """Serialize a PMW2 shard from frames already produced by :func:`encode_frame`."""
    header = _FILE_HEADER.pack(
        PMW2_MAGIC,
        PMW2_VERSION,
        FILE_HEADER_BYTES,
        run_id,
        shard_index,
        adc_bits,
        len(frames),
        0,
    )
    return header + b"".join(frames)
ORACLE_PMWIO_DECODER_PY

cat > pretrig/robust.py <<'ORACLE_PRETRIG_ROBUST_PY'
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
ORACLE_PRETRIG_ROBUST_PY

cat > qualitygate/quality.py <<'ORACLE_QUALITYGATE_QUALITY_PY'
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
ORACLE_QUALITYGATE_QUALITY_PY

cat > reducectl/run.py <<'ORACLE_REDUCECTL_RUN_PY'
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
ORACLE_REDUCECTL_RUN_PY

find /app/environment -name '__pycache__' -type d -prune -exec rm -rf {} +

python3 hvreduce.py calibrate hv-raw-a
python3 hvreduce.py calibrate hv-norm-b
python3 hvreduce.py calibrate hv-interleave-c
python3 hvreduce.py calibrate hv-neg-edge-d
