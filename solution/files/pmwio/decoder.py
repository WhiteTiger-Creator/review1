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
