"""Independent reference reduction for the offline PMT waveform calibration.

This module belongs to the verification suite alone. It re-derives the two
published artifacts straight from the contract written under
``docs/`` and shares no code with the workspace under test: nothing
here imports ``acquire``, ``catalog``, ``integrate``, ``offset``, ``pedestal``,
``publish``, ``regress``, or ``session``.

The reduction is deliberately organised differently from any production layout.
The whole pipeline is one flat module, the container is parsed with an explicit
validation ladder, the pedestal population is a plain list slice rather than a
ring buffer, and the generalized least squares system is solved by applying
``numpy.linalg.solve`` to the measurement covariance directly instead of
whitening the design with a Cholesky factor. The published numbers are
nevertheless the same numbers, because both routes evaluate the same contract.

The module also owns the PMW2 encoder and the synthetic waveform builder the
hidden test cases use, so that no fixture in the suite is produced by the code
being graded.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import tomllib

# --------------------------------------------------------------------------
# Contract constants (docs/overview.md, "Constants")
# --------------------------------------------------------------------------

SCHEMA_VERSION = 2

CONTAINER_MAGIC = b"PMW2"
CONTAINER_VERSION = 2
FILE_HEADER_BYTES = 24
FRAME_HEADER_BYTES = 28
LEGAL_ADC_BITS = (12, 14)
SAMPLE_COUNT_MIN = 64
SAMPLE_COUNT_MAX = 512

KIND_PEDESTAL = 0
KIND_PULSER = 1
LEGAL_KINDS = (KIND_PEDESTAL, KIND_PULSER)
LEGAL_POLARITIES = (1, -1)

PRE_TRIGGER = 32
INTEGRATION_HALF_WIDTH = 8
GATE_WIDTH = 2 * INTEGRATION_HALF_WIDTH + 1
MIN_COVERAGE = 0.70
OUTLIER_K = 3.0
MAD_SCALE = 1.4826
MIN_BASELINE_SAMPLES = 8
QUANTIZATION_VAR = 1.0 / 12.0
MEDIAN_VARIANCE_FACTOR = math.pi / 2.0
PILEUP_FRAC = 0.35
PILEUP_SEP = 6

PEDESTAL_K = 8
PEDESTAL_P = 4
PEDESTAL_VAR_FLOOR = 1.0
NOISE_SIGMA_LIMIT = 12.0

MIN_OBS = 6
MIN_DISTINCT_LEVELS = 3
COND_THRESHOLD = 1.0e12
COMMON_MODE_SCALE = 0.25

PUBLICATION_DIGITS = 9
NS_PER_SECOND = 1.0e9

FIT_PARAMETERS = 3

STATUS_OK = "ok"
STATUS_NOISY = "noisy"
STATUS_INSUFFICIENT = "insufficient"
STATUS_SINGULAR = "singular"

_FILE_HEADER = struct.Struct("<4sHHIHHII")
_FRAME_HEADER = struct.Struct("<HHIIqHhI")


# --------------------------------------------------------------------------
# Container model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Acquisition:
    """One validated PMW2 frame together with the shard it came from."""

    run_id: int
    lane_id: int
    acq_seq: int
    kind: int
    pulser_level: int
    timestamp_ns: int
    sample_count: int
    polarity: int
    adc_bits: int
    samples: tuple[int, ...]
    shard_basename: str
    shard_index: int

    def key(self) -> tuple[int, int, int]:
        """Acquisition identity: ``(run_id, lane_id, acq_seq)``."""
        return (self.run_id, self.lane_id, self.acq_seq)

    def body(self) -> tuple[int, int, int, int, int, tuple[int, ...]]:
        """Everything outside the identity two crates may disagree on."""
        return (
            self.kind,
            self.pulser_level,
            self.timestamp_ns,
            self.sample_count,
            self.polarity,
            self.samples,
        )

    def order_key(self) -> tuple[int, int, int, int]:
        """Documented process order: timestamp, kind, lane, sequence."""
        return (self.timestamp_ns, self.kind, self.lane_id, self.acq_seq)


@dataclass(frozen=True)
class Container:
    """One decoded PMW2 shard image."""

    basename: str
    run_id: int
    shard_index: int
    adc_bits: int
    byte_length: int
    sha256_hex: str
    acquisitions: tuple[Acquisition, ...]

    def rank(self) -> tuple[int, str]:
        """Merge priority; ascending, basename breaking ``shard_index`` ties."""
        return (self.shard_index, self.basename)


class ContractError(ValueError):
    """Raised when an input violates the documented contract."""


def rail_bounds(adc_bits: int) -> tuple[int, int]:
    """Digitizer rails ``(low, high)`` for a crate of ``adc_bits`` bits."""
    if adc_bits not in LEGAL_ADC_BITS:
        raise ContractError(f"unsupported adc_bits {adc_bits}")
    half = 1 << (adc_bits - 1)
    return -half, half - 1


def decode_container(blob: bytes, basename: str) -> Container:
    """Decode one in-memory PMW2 image, validating in file order.

    The validation ladder and the wording of every message follow
    ``docs/container.md``, section *Decoder validation*.
    """
    if len(blob) < FILE_HEADER_BYTES or blob[:4] != CONTAINER_MAGIC:
        raise ContractError(f"unrecognized PMW2 shard {basename}")

    (
        _magic,
        version,
        header_bytes,
        run_id,
        shard_index,
        adc_bits,
        frame_count,
        reserved,
    ) = _FILE_HEADER.unpack_from(blob, 0)

    if version != CONTAINER_VERSION:
        raise ContractError(f"unsupported PMW2 version {version} in {basename}")
    if header_bytes != FILE_HEADER_BYTES:
        raise ContractError(f"unexpected file header size {header_bytes} in {basename}")
    if adc_bits not in LEGAL_ADC_BITS:
        raise ContractError(f"unsupported adc_bits {adc_bits} in {basename}")
    if reserved != 0:
        raise ContractError(f"reserved file header field must be zero in {basename}")

    low, high = rail_bounds(adc_bits)
    cursor = FILE_HEADER_BYTES
    decoded: list[Acquisition] = []

    for _ in range(frame_count):
        if cursor + FRAME_HEADER_BYTES > len(blob):
            raise ContractError(f"truncated PMW2 frame in {basename}")
        (
            lane_id,
            kind,
            acq_seq,
            pulser_level,
            timestamp_ns,
            sample_count,
            polarity,
            crc32,
        ) = _FRAME_HEADER.unpack_from(blob, cursor)
        cursor += FRAME_HEADER_BYTES

        if not SAMPLE_COUNT_MIN <= sample_count <= SAMPLE_COUNT_MAX:
            raise ContractError(f"sample_count out of range {sample_count} {basename}")
        if kind not in LEGAL_KINDS:
            raise ContractError(f"unknown frame kind {kind} in {basename}")
        if polarity not in LEGAL_POLARITIES:
            raise ContractError(f"invalid polarity {polarity} in {basename}")

        stop = cursor + 2 * sample_count
        if stop > len(blob):
            raise ContractError(f"truncated PMW2 frame in {basename}")
        payload = blob[cursor:stop]
        samples = struct.unpack(f"<{sample_count}h", payload)
        if min(samples) < low or max(samples) > high:
            raise ContractError(f"sample out of range for adc_bits in {basename}")
        if (zlib.crc32(payload) & 0xFFFFFFFF) != crc32:
            raise ContractError(f"sample payload CRC mismatch in {basename}")
        cursor = stop

        decoded.append(
            Acquisition(
                run_id=run_id,
                lane_id=lane_id,
                acq_seq=acq_seq,
                kind=kind,
                pulser_level=pulser_level,
                timestamp_ns=timestamp_ns,
                sample_count=sample_count,
                polarity=polarity,
                adc_bits=adc_bits,
                samples=samples,
                shard_basename=basename,
                shard_index=shard_index,
            )
        )

    if cursor != len(blob):
        raise ContractError(f"trailing bytes after final frame in {basename}")

    return Container(
        basename=basename,
        run_id=run_id,
        shard_index=shard_index,
        adc_bits=adc_bits,
        byte_length=len(blob),
        sha256_hex=hashlib.sha256(blob).hexdigest(),
        acquisitions=tuple(decoded),
    )


def read_container(path: Path) -> Container:
    """Read one shard file from disk and decode it."""
    try:
        blob = path.read_bytes()
    except OSError as err:
        raise ContractError(f"missing shard {path.name}") from err
    return decode_container(blob, path.name)


# --------------------------------------------------------------------------
# Verifier-owned encoder (used to build hidden fixtures)
# --------------------------------------------------------------------------


def encode_acquisition(
    *,
    lane_id: int,
    kind: int,
    acq_seq: int,
    pulser_level: int,
    timestamp_ns: int,
    polarity: int,
    samples: Sequence[int],
    declared_sample_count: int | None = None,
    crc_override: int | None = None,
) -> bytes:
    """Serialise one frame header plus payload.

    ``declared_sample_count`` and ``crc_override`` exist so the decoder
    rejection cases can build deliberately malformed containers.
    """
    payload = struct.pack(f"<{len(samples)}h", *samples)
    crc = zlib.crc32(payload) & 0xFFFFFFFF if crc_override is None else crc_override
    count = len(samples) if declared_sample_count is None else declared_sample_count
    header = _FRAME_HEADER.pack(
        lane_id,
        kind,
        acq_seq,
        pulser_level,
        timestamp_ns,
        count,
        polarity,
        crc,
    )
    return header + payload


def encode_container(
    *,
    run_id: int,
    shard_index: int,
    adc_bits: int,
    frames: Sequence[bytes],
    version: int = CONTAINER_VERSION,
    header_bytes: int = FILE_HEADER_BYTES,
    reserved: int = 0,
    magic: bytes = CONTAINER_MAGIC,
    declared_frame_count: int | None = None,
    tail: bytes = b"",
) -> bytes:
    """Serialise a whole PMW2 shard from already encoded frames."""
    count = len(frames) if declared_frame_count is None else declared_frame_count
    head = _FILE_HEADER.pack(
        magic,
        version,
        header_bytes,
        run_id,
        shard_index,
        adc_bits,
        count,
        reserved,
    )
    return head + b"".join(frames) + tail


# --------------------------------------------------------------------------
# Shard set and merge
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeTally:
    """The three merge counters published under ``provenance``."""

    frames_read: int
    frames_rejected_duplicate: int
    frames_conflicting: int


def agreed_run_configuration(containers: Sequence[Container]) -> tuple[int, int]:
    """The ``(run_id, adc_bits)`` every shard of one profile must share."""
    if not containers:
        raise ContractError("profile has no acquisition shards")
    runs = {container.run_id for container in containers}
    if len(runs) != 1:
        raise ContractError(f"mixed run_id across profile shards {sorted(runs)}")
    widths = {container.adc_bits for container in containers}
    if len(widths) != 1:
        raise ContractError(f"mixed adc_bits across profile shards {sorted(widths)}")
    return runs.pop(), widths.pop()


def consolidate(
    containers: Sequence[Container],
) -> tuple[list[Acquisition], MergeTally]:
    """Deduplicate identities by shard rank, then sort into process order."""
    held: dict[tuple[int, int, int], Acquisition] = {}
    read = 0
    dropped = 0
    conflicts = 0

    for container in sorted(containers, key=Container.rank):
        for frame in container.acquisitions:
            read += 1
            incumbent = held.get(frame.key())
            if incumbent is None:
                held[frame.key()] = frame
            else:
                dropped += 1
                if incumbent.body() != frame.body():
                    conflicts += 1

    survivors = sorted(held.values(), key=Acquisition.order_key)
    return survivors, MergeTally(read, dropped, conflicts)


# --------------------------------------------------------------------------
# Robust statistics
# --------------------------------------------------------------------------


def central_value(values: Sequence[float]) -> float:
    """Population median; even lengths average the two central order stats."""
    if len(values) == 0:
        return 0.0
    return float(np.median(np.asarray(values, dtype=np.float64)))


def deviation_scale(values: Sequence[float], centre: float) -> float:
    """Median absolute deviation of ``values`` about ``centre``."""
    if len(values) == 0:
        return 0.0
    array = np.abs(np.asarray(values, dtype=np.float64) - centre)
    return float(np.median(array))


# --------------------------------------------------------------------------
# Frame reduction
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Pedestrial:
    """Pre-trigger baseline estimate and the variances derived from it."""

    level: float
    sigma: float
    noise_var: float
    location_var: float
    retained: int


@dataclass(frozen=True)
class GateResult:
    """The outcome of reducing one frame: gate charge plus a verdict."""

    verdict: str
    charge: float
    charge_var: float
    coverage: float
    gate_samples: int
    peak_index: int
    base: Pedestrial


VERDICT_REDUCED = "reduced"
VERDICT_SATURATED = "saturated"
VERDICT_COVERAGE = "coverage"
VERDICT_PILEUP = "pileup"


def pre_trigger_estimate(samples: Sequence[int]) -> Pedestrial:
    """Two-pass robust baseline over ``samples[0 .. PRE_TRIGGER-1]``."""
    window = [float(value) for value in samples[:PRE_TRIGGER]]
    provisional = central_value(window)
    scale_first = MAD_SCALE * deviation_scale(window, provisional)

    if scale_first == 0.0:
        kept = window
    else:
        limit = OUTLIER_K * scale_first
        kept = [value for value in window if abs(value - provisional) <= limit]

    if len(kept) < MIN_BASELINE_SAMPLES:
        level = provisional
        sigma = scale_first
        retained = len(window)
    else:
        level = central_value(kept)
        sigma = MAD_SCALE * deviation_scale(kept, level)
        retained = len(kept)

    noise_var = max(sigma * sigma, QUANTIZATION_VAR)
    location_var = MEDIAN_VARIANCE_FACTOR * noise_var / retained if retained else 0.0
    return Pedestrial(level, sigma, noise_var, location_var, retained)


def touches_rail(samples: Sequence[int], adc_bits: int) -> bool:
    """True when any raw sample sits on either digitizer rail."""
    low, high = rail_bounds(adc_bits)
    return min(samples) <= low or max(samples) >= high


def _gate_span(kind: int, corrected: Sequence[float]) -> tuple[int, int, int]:
    """Return ``(peak, lo, hi)`` for the integration gate of one frame."""
    if kind == KIND_PEDESTAL:
        peak = PRE_TRIGGER + INTEGRATION_HALF_WIDTH
        return peak, PRE_TRIGGER, PRE_TRIGGER + 2 * INTEGRATION_HALF_WIDTH

    peak = PRE_TRIGGER
    for index in range(PRE_TRIGGER + 1, len(corrected)):
        if corrected[index] > corrected[peak]:
            peak = index
    lo = max(0, peak - INTEGRATION_HALF_WIDTH)
    hi = min(len(corrected) - 1, peak + INTEGRATION_HALF_WIDTH)
    return peak, lo, hi


def _shoulder(corrected: Sequence[float], peak: int) -> float | None:
    """Largest post-trigger excursion further than ``PILEUP_SEP`` from ``peak``."""
    best: float | None = None
    for index in range(PRE_TRIGGER, len(corrected)):
        if abs(index - peak) <= PILEUP_SEP:
            continue
        value = corrected[index]
        if best is None or value > best:
            best = value
    return best


def reduce_acquisition(frame: Acquisition) -> GateResult:
    """Baseline, polarity, gate integration, and the frame-quality ladder."""
    base = pre_trigger_estimate(frame.samples)

    if touches_rail(frame.samples, frame.adc_bits):
        return GateResult(VERDICT_SATURATED, 0.0, 0.0, 0.0, 0, -1, base)

    corrected = [frame.polarity * (float(v) - base.level) for v in frame.samples]
    peak, lo, hi = _gate_span(frame.kind, corrected)

    gate_samples = hi - lo + 1
    charge = sum(corrected[lo : hi + 1])
    coverage = gate_samples / GATE_WIDTH
    charge_var = (
        gate_samples * base.noise_var + gate_samples**2 * base.location_var
    )

    verdict = VERDICT_REDUCED
    if frame.kind != KIND_PEDESTAL:
        if coverage < MIN_COVERAGE:
            verdict = VERDICT_COVERAGE
        else:
            shoulder = _shoulder(corrected, peak)
            if (
                shoulder is not None
                and shoulder > 0.0
                and shoulder >= PILEUP_FRAC * corrected[peak]
            ):
                verdict = VERDICT_PILEUP

    return GateResult(
        verdict, charge, charge_var, coverage, gate_samples, peak, base
    )


# --------------------------------------------------------------------------
# Rolling pedestal population
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowSnapshot:
    """A lane's rolling pedestal population summarised at one moment."""

    charge: float
    sigma: float
    variance: float
    epoch: int
    size: int


class LaneLedger:
    """Per-lane pedestal history kept as a plain list with a tail slice."""

    def __init__(self) -> None:
        self._history: dict[int, list[float]] = {}
        self._counter: dict[int, int] = {}

    def append(self, lane_id: int, charge: float) -> None:
        """Record one reduced pedestal charge and advance the lane's epoch."""
        self._history.setdefault(lane_id, []).append(charge)
        self._counter[lane_id] = self._counter.get(lane_id, 0) + 1

    def window(self, lane_id: int) -> list[float]:
        """The most recent ``PEDESTAL_K`` charges recorded for ``lane_id``."""
        return self._history.get(lane_id, [])[-PEDESTAL_K:]

    def snapshot(self, lane_id: int) -> WindowSnapshot:
        """Robust summary of ``lane_id``'s window as of right now."""
        window = self.window(lane_id)
        epoch = self._counter.get(lane_id, 0)
        if not window:
            return WindowSnapshot(0.0, 0.0, PEDESTAL_VAR_FLOOR, epoch, 0)
        centre = central_value(window)
        sigma = MAD_SCALE * deviation_scale(window, centre)
        variance = max(sigma * sigma, PEDESTAL_VAR_FLOOR)
        return WindowSnapshot(centre, sigma, variance, epoch, len(window))


# --------------------------------------------------------------------------
# Generalized least squares
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Datum:
    """One admitted pulser observation with its frozen pedestal context."""

    level: int
    seconds: float
    charge: float
    variance: float
    epoch: int


@dataclass(frozen=True)
class LaneFit:
    """Fitted parameters, diagnostics, and the status of one lane."""

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


def _blank_fit(status: str, n_obs: int, distinct_levels: int) -> LaneFit:
    return LaneFit(
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


def measurement_covariance(
    data: Sequence[Datum], *, common_mode: bool = True
) -> np.ndarray:
    """Diagonal variances plus the shared-pedestal common-mode off-diagonal.

    ``common_mode=False`` reproduces the ordinary weighted fit the contract
    explicitly rules out; the suite uses it to show the block matters.
    """
    diagonal = np.array([datum.variance for datum in data], dtype=np.float64)
    matrix = np.diag(diagonal)
    if not common_mode:
        return matrix

    grouped: dict[int, list[int]] = {}
    for index, datum in enumerate(data):
        grouped.setdefault(datum.epoch, []).append(index)

    for members in grouped.values():
        if len(members) < 2:
            continue
        share = COMMON_MODE_SCALE * float(np.mean(diagonal[members]))
        block = np.ix_(members, members)
        addition = np.full((len(members), len(members)), share, dtype=np.float64)
        np.fill_diagonal(addition, 0.0)
        matrix[block] += addition
    return matrix


def _cholesky_admits(matrix: np.ndarray) -> bool:
    """True when ``matrix`` factors as ``L L^T``; a direct positive-definite test.

    Written out here rather than delegated, because the status the contract
    attaches to a covariance that will not factor is part of what is graded.
    """
    size = matrix.shape[0]
    lower = np.zeros_like(matrix)
    for row in range(size):
        for column in range(row + 1):
            total = matrix[row, column] - float(
                lower[row, :column] @ lower[column, :column]
            )
            if row == column:
                if not total > 0.0 or not math.isfinite(total):
                    return False
                lower[row, column] = math.sqrt(total)
            else:
                lower[row, column] = total / lower[column, column]
    return True


def solve_lane(
    data: Sequence[Datum],
    *,
    noisy_rejections: int,
    common_mode: bool = True,
) -> LaneFit:
    """Classify one lane and, when it qualifies, solve its GLS fit."""
    count = len(data)
    distinct_levels = len({datum.level for datum in data})

    if count < MIN_OBS and noisy_rejections > 0:
        return _blank_fit(STATUS_NOISY, count, distinct_levels)
    if count < MIN_OBS or distinct_levels < MIN_DISTINCT_LEVELS:
        return _blank_fit(STATUS_INSUFFICIENT, count, distinct_levels)

    seconds = np.array([datum.seconds for datum in data], dtype=np.float64)
    origin = float(seconds.mean())
    design = np.empty((count, FIT_PARAMETERS), dtype=np.float64)
    design[:, 0] = 1.0
    design[:, 1] = [float(datum.level) for datum in data]
    design[:, 2] = seconds - origin
    response = np.array([datum.charge for datum in data], dtype=np.float64)

    covariance = measurement_covariance(data, common_mode=common_mode)
    if not _cholesky_admits(covariance):
        return _blank_fit(STATUS_SINGULAR, count, distinct_levels)

    try:
        weighted_design = np.linalg.solve(covariance, design)
        weighted_response = np.linalg.solve(covariance, response)
        gram = design.T @ weighted_design
        gram_inverse = np.linalg.inv(gram)
        beta = np.linalg.solve(gram, design.T @ weighted_response)
    except np.linalg.LinAlgError:
        return _blank_fit(STATUS_SINGULAR, count, distinct_levels)

    cond = float(np.linalg.norm(gram, 1) * np.linalg.norm(gram_inverse, 1))
    if not math.isfinite(cond) or cond > COND_THRESHOLD:
        return _blank_fit(STATUS_SINGULAR, count, distinct_levels)

    residual = response - design @ beta
    chi2 = float(residual @ np.linalg.solve(covariance, residual))
    dof = count - FIT_PARAMETERS
    diag = [float(gram_inverse[i, i]) for i in range(FIT_PARAMETERS)]
    sigma = [math.sqrt(value) if value > 0.0 else 0.0 for value in diag]

    return LaneFit(
        status=STATUS_OK,
        n_obs=count,
        distinct_levels=distinct_levels,
        intercept=float(beta[0]),
        intercept_sigma=sigma[0],
        gain=float(beta[1]),
        gain_sigma=sigma[1],
        gain_var=diag[1],
        drift=float(beta[2]),
        drift_sigma=sigma[2],
        t0=origin,
        chi2=chi2,
        dof=dof,
        chi2_per_dof=chi2 / dof if dof > 0 else None,
        cond=cond,
    )


# --------------------------------------------------------------------------
# Reference-lane normalization
# --------------------------------------------------------------------------


def published_gains(
    fits: dict[int, LaneFit],
    reference_lane: int | None,
    shared_source_var: float,
    *,
    cross_term: bool = True,
) -> dict[int, tuple[float, float]]:
    """Map every lane onto its published ``(gain, gain_sigma)`` pair.

    ``cross_term=False`` drops the delta-method covariance contribution, which
    the contract requires; the suite uses it to show the term is observable.
    """
    if reference_lane is None:
        return {lane: (fit.gain, fit.gain_sigma) for lane, fit in fits.items()}

    anchor = fits.get(reference_lane)
    if anchor is None:
        raise ContractError(f"reference lane {reference_lane} has no row")
    if anchor.status != STATUS_OK:
        raise ContractError(f"reference lane {reference_lane} is not ok")
    if not anchor.gain > 0.0:
        raise ContractError(f"reference lane {reference_lane} gain is not positive")

    scale = anchor.gain
    anchor_var = anchor.gain_var
    covariance = shared_source_var if cross_term else 0.0

    out: dict[int, tuple[float, float]] = {}
    for lane, fit in fits.items():
        if lane == reference_lane:
            out[lane] = (1.0, 0.0)
            continue
        if fit.status != STATUS_OK:
            out[lane] = (0.0, 0.0)
            continue
        ratio_var = (
            fit.gain_var / scale**2
            + fit.gain**2 * anchor_var / scale**4
            - 2.0 * fit.gain * covariance / scale**3
        )
        sigma = math.sqrt(ratio_var) if ratio_var > 0.0 else 0.0
        out[lane] = (fit.gain / scale, sigma)
    return out


# --------------------------------------------------------------------------
# Publication
# --------------------------------------------------------------------------


def round_published(value: float) -> float:
    """Round one float to ``PUBLICATION_DIGITS`` places, mapping ``-0.0``."""
    rounded = round(float(value), PUBLICATION_DIGITS)
    return 0.0 if rounded == 0.0 else rounded


def compact_bytes(payload: Any) -> bytes:
    """Documented encoding used by both digests."""
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


def digest_without(document: dict[str, Any], key: str) -> str:
    """Digest of ``document`` with ``key`` removed, as both bindings require."""
    body = {name: value for name, value in document.items() if name != key}
    return content_digest(body)


# --------------------------------------------------------------------------
# Profile table
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileSpec:
    """One profile section of ``runbook/campaign.toml``."""

    name: str
    shards: tuple[str, ...]
    reference_lane: int | None
    shared_source_var: float


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def profiles_path(env_root: Path) -> Path:
    """Location of the operator profile table inside a workspace."""
    return env_root / "runbook" / "campaign.toml"


def read_profile(env_root: Path, name: str) -> ProfileSpec:
    """Parse one profile declaration as TOML, following the documented rules."""
    with profiles_path(env_root).open("rb") as handle:
        document = tomllib.load(handle)

    tables = {key: value for key, value in document.items() if isinstance(value, dict)}
    if name not in tables:
        raise ContractError(f"unknown profile {name}")
    table = tables[name]

    declared = table.get("shards")
    if type(declared) is not list or not declared:
        raise ContractError(f"profile has no acquisition shards {name}")

    reference_lane = table.get("reference_lane")
    if reference_lane is not None and not _is_integer(reference_lane):
        raise ContractError(f"profile {name} reference_lane must be an integer")

    shared = table.get("shared_source_var", 0.0)
    if not _is_number(shared):
        raise ContractError(f"profile {name} shared_source_var must be a number")

    return ProfileSpec(
        name=name,
        shards=tuple(str(item) for item in declared),
        reference_lane=reference_lane,
        shared_source_var=float(shared),
    )


# --------------------------------------------------------------------------
# Whole-run reduction
# --------------------------------------------------------------------------

_TALLY_KEYS = (
    "pedestal_frames",
    "frames_rejected_saturation",
    "frames_rejected_coverage",
    "frames_rejected_pileup",
    "frames_rejected_no_pedestal",
    "frames_rejected_noisy",
    "frames_accepted",
)


@dataclass
class Walk:
    """Everything the single pass over the merged frames produces."""

    ledger: LaneLedger
    lanes: set[int] = field(default_factory=set)
    data: dict[int, list[Datum]] = field(default_factory=dict)
    noisy: dict[int, int] = field(default_factory=dict)
    tally: dict[str, int] = field(default_factory=dict)


def walk_frames(frames: Sequence[Acquisition]) -> Walk:
    """Walk merged frames once, in documented process order, without look-ahead."""
    walk = Walk(ledger=LaneLedger(), tally=dict.fromkeys(_TALLY_KEYS, 0))

    for frame in frames:
        walk.lanes.add(frame.lane_id)
        outcome = reduce_acquisition(frame)

        if outcome.verdict == VERDICT_SATURATED:
            walk.tally["frames_rejected_saturation"] += 1
            continue

        if frame.kind == KIND_PEDESTAL:
            walk.ledger.append(frame.lane_id, outcome.charge)
            walk.tally["pedestal_frames"] += 1
            continue

        if outcome.verdict == VERDICT_COVERAGE:
            walk.tally["frames_rejected_coverage"] += 1
            continue
        if outcome.verdict == VERDICT_PILEUP:
            walk.tally["frames_rejected_pileup"] += 1
            continue

        snapshot = walk.ledger.snapshot(frame.lane_id)
        if snapshot.size < PEDESTAL_P:
            walk.tally["frames_rejected_no_pedestal"] += 1
            continue
        if snapshot.sigma > NOISE_SIGMA_LIMIT:
            walk.tally["frames_rejected_noisy"] += 1
            walk.noisy[frame.lane_id] = walk.noisy.get(frame.lane_id, 0) + 1
            continue

        walk.data.setdefault(frame.lane_id, []).append(
            Datum(
                level=frame.pulser_level,
                seconds=frame.timestamp_ns / NS_PER_SECOND,
                charge=outcome.charge - outcome.coverage * snapshot.charge,
                variance=(
                    outcome.charge_var + outcome.coverage**2 * snapshot.variance
                ),
                epoch=snapshot.epoch,
            )
        )
        walk.tally["frames_accepted"] += 1

    return walk


def contract_gain_table(
    env_root: Path,
    profile_name: str,
    *,
    common_mode: bool = True,
    cross_term: bool = True,
) -> dict[str, Any]:
    """Reduce one profile end to end and return the report the contract implies.

    The two keyword switches produce deliberately wrong variants used by the
    suite to demonstrate that the common-mode block and the delta-method cross
    term are observable in the published numbers.
    """
    spec = read_profile(env_root, profile_name)
    fixtures = env_root / "fixtures"
    containers = [read_container(fixtures / name) for name in spec.shards]
    run_id, adc_bits = agreed_run_configuration(containers)

    frames, merge_tally = consolidate(containers)
    walk = walk_frames(frames)

    fits = {
        lane: solve_lane(
            walk.data.get(lane, []),
            noisy_rejections=walk.noisy.get(lane, 0),
            common_mode=common_mode,
        )
        for lane in sorted(walk.lanes)
    }
    gains = published_gains(
        fits, spec.reference_lane, spec.shared_source_var, cross_term=cross_term
    )

    rows: list[dict[str, Any]] = []
    for lane, fit in fits.items():
        snapshot = walk.ledger.snapshot(lane)
        gain, gain_sigma = gains[lane]
        rows.append(
            {
                "lane_id": lane,
                "status": fit.status,
                "n_obs": fit.n_obs,
                "distinct_levels": fit.distinct_levels,
                "pedestal_charge": round_published(snapshot.charge),
                "pedestal_sigma": round_published(snapshot.sigma),
                "gain": round_published(gain),
                "gain_sigma": round_published(gain_sigma),
                "intercept": round_published(fit.intercept),
                "intercept_sigma": round_published(fit.intercept_sigma),
                "drift": round_published(fit.drift),
                "drift_sigma": round_published(fit.drift_sigma),
                "t0": round_published(fit.t0),
                "chi2": round_published(fit.chi2),
                "dof": fit.dof,
                "chi2_per_dof": (
                    None
                    if fit.chi2_per_dof is None
                    else round_published(fit.chi2_per_dof)
                ),
                "cond": round_published(fit.cond),
            }
        )

    fitted = sum(1 for fit in fits.values() if fit.status == STATUS_OK)
    provenance = {
        "frames_read": merge_tally.frames_read,
        "frames_rejected_duplicate": merge_tally.frames_rejected_duplicate,
        "frames_conflicting": merge_tally.frames_conflicting,
        "pedestal_frames": walk.tally["pedestal_frames"],
        "frames_rejected_saturation": walk.tally["frames_rejected_saturation"],
        "frames_rejected_coverage": walk.tally["frames_rejected_coverage"],
        "frames_rejected_pileup": walk.tally["frames_rejected_pileup"],
        "frames_rejected_no_pedestal": walk.tally["frames_rejected_no_pedestal"],
        "frames_rejected_noisy": walk.tally["frames_rejected_noisy"],
        "frames_accepted": walk.tally["frames_accepted"],
        "lanes_fitted": fitted,
        "lanes_rejected": len(fits) - fitted,
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "profile": spec.name,
        "run_id": run_id,
        "adc_bits": adc_bits,
        "reference_lane": spec.reference_lane,
        "normalized": spec.reference_lane is not None,
        "input_shards": sorted(item.basename for item in containers),
        "provenance": provenance,
        "lanes": rows,
    }
    report["calibration_digest"] = digest_without(report, "calibration_digest")
    return report


def expected_state(report: dict[str, Any]) -> dict[str, Any]:
    """Derive the replay state that must accompany ``report``."""
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "last_profile": report["profile"],
        "last_run_id": report["run_id"],
        "adc_bits": report["adc_bits"],
        "lane_count": len(report["lanes"]),
        "lanes_fitted": report["provenance"]["lanes_fitted"],
        "calibration_digest": report["calibration_digest"],
    }
    state["replay_fingerprint"] = digest_without(state, "replay_fingerprint")
    return state


# --------------------------------------------------------------------------
# Synthetic waveform builder for the hidden cases
# --------------------------------------------------------------------------

DEFAULT_SAMPLES = 96
DEFAULT_PEAK = 44
PULSE_HALF_LIFE = 5.0
TWIN_OFFSET = 11
TWIN_SCALE = 0.55


@dataclass(frozen=True)
class Beat:
    """One scheduled acquisition on a synthetic lane."""

    kind: int
    level: int = 0
    peak: int = DEFAULT_PEAK
    saturate: bool = False
    twin: bool = False
    wobble: float = 0.0
    share_previous_time: bool = False
    freeze_time: bool = False


@dataclass(frozen=True)
class LaneRecipe:
    """Physical description of one synthetic readout lane."""

    lane_id: int
    baseline: float
    gain: float
    drift: float
    pedestal_excursion: float
    schedule: tuple[Beat, ...]
    noise_sigma: float = 1.0
    sample_count: int = DEFAULT_SAMPLES
    level_scale: float = 1.0


def pedestal_beats(count: int, *, wobble: float = 0.0) -> list[Beat]:
    """A block of ``count`` pedestal acquisitions."""
    return [Beat(kind=KIND_PEDESTAL, wobble=wobble) for _ in range(count)]


def pulse_beat(level: int, **kwargs: Any) -> list[Beat]:
    """A single pulser acquisition at ``level``."""
    return [Beat(kind=KIND_PULSER, level=level, **kwargs)]


def _ramp(index: int, centre: float) -> float:
    return max(0.0, 1.0 - abs(index - centre) / PULSE_HALF_LIFE)


def _trace(
    rng: random.Random,
    recipe: LaneRecipe,
    beat: Beat,
    *,
    polarity: int,
    adc_bits: int,
    elapsed: float,
    wobble_sign: int,
) -> list[int]:
    low, high = rail_bounds(adc_bits)
    excursion = recipe.pedestal_excursion + beat.wobble * wobble_sign
    amplitude = 0.0
    if beat.kind == KIND_PULSER:
        excursion += recipe.drift * elapsed
        amplitude = beat.level * recipe.gain * recipe.level_scale

    values: list[int] = []
    for index in range(recipe.sample_count):
        value = recipe.baseline + rng.gauss(0.0, recipe.noise_sigma)
        if index >= PRE_TRIGGER:
            shape = excursion
            if amplitude:
                shape += amplitude * _ramp(index, beat.peak)
                if beat.twin:
                    shape += (
                        TWIN_SCALE * amplitude * _ramp(index, beat.peak + TWIN_OFFSET)
                    )
            value += polarity * shape
        values.append(max(low + 1, min(high - 1, round(value))))

    if beat.saturate:
        values[beat.peak] = high if polarity > 0 else low
    return values


def synth_lane(
    recipe: LaneRecipe,
    *,
    seed: int,
    polarity: int = 1,
    adc_bits: int = 12,
    base_timestamp_ns: int = 2_000_000_000,
    step_ns: int = 3_000_000_000,
    sample_shift: int = 0,
    level_map: Callable[[int], int] | None = None,
    time_map: Callable[[int], int] | None = None,
) -> list[bytes]:
    """Encode one synthetic lane's whole schedule into PMW2 frames.

    ``sample_shift``, ``level_map``, and ``time_map`` exist for the metamorphic
    cases: they translate the digitizer codes, reparameterize the drive levels,
    and reparameterize the acquisition times without touching anything else.
    """
    rng = random.Random(seed)
    frames: list[bytes] = []
    wobble_index = 0
    previous_time: int | None = None
    frozen: int | None = None

    for position, beat in enumerate(recipe.schedule):
        acq_seq = position + 1
        timestamp_ns = base_timestamp_ns + position * step_ns
        if beat.share_previous_time and previous_time is not None:
            timestamp_ns = previous_time
        if beat.freeze_time:
            frozen = timestamp_ns if frozen is None else frozen
            timestamp_ns = frozen
        previous_time = timestamp_ns

        elapsed = (timestamp_ns - base_timestamp_ns) / NS_PER_SECOND
        sign = 1 if wobble_index % 2 == 0 else -1
        samples = _trace(
            rng,
            recipe,
            beat,
            polarity=polarity,
            adc_bits=adc_bits,
            elapsed=elapsed,
            wobble_sign=sign,
        )
        if beat.kind == KIND_PEDESTAL:
            wobble_index += 1
        if sample_shift:
            samples = [value + sample_shift for value in samples]

        level = beat.level
        if level_map is not None and beat.kind == KIND_PULSER:
            level = level_map(beat.level)
        emitted_time = timestamp_ns if time_map is None else time_map(timestamp_ns)

        frames.append(
            encode_acquisition(
                lane_id=recipe.lane_id,
                kind=beat.kind,
                acq_seq=acq_seq,
                pulser_level=level,
                timestamp_ns=emitted_time,
                polarity=polarity,
                samples=samples,
            )
        )
    return frames
