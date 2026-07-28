"""Deterministic PMW2 acquisition fixture generator.

Writes the bundled shards under ``fixtures/`` that the profiles in
``runbook/campaign.toml`` name. The generator is self-contained on purpose: it runs
at image build time, before the reduction packages are known to be healthy, and
it must emit byte-identical shards on every run.

Run it from the workspace root:

    python3 fixturekit/gen_fixtures.py
"""

from __future__ import annotations

import random
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

_FILE_HEADER = struct.Struct("<4sHHIHHII")
_FRAME_HEADER = struct.Struct("<HHIIqHhI")

MAGIC = b"PMW2"
VERSION = 2
HEADER_BYTES = 24

SAMPLE_COUNT = 96
PRE_TRIGGER = 32
PULSE_WIDTH = 5.0
DEFAULT_PEAK = 44
NOISE_SIGMA = 1.0
# Crate dither: cancels over any four consecutive codes, so it leaves the
# pre-trigger median untouched while keeping the window spread over several
# ADC codes instead of collapsing onto one.
DITHER_AMPLITUDE = 1.6
DITHER_PATTERN = (-1.0, -1.0 / 3.0, 1.0 / 3.0, 1.0)
UNSTABLE_SHIFT = 1.6
PILEUP_OFFSET = 11
PILEUP_SCALE = 0.55

KIND_PEDESTAL = 0
KIND_PULSER = 1

BASE_TIMESTAMP_NS = 1_000_000_000
STEP_NS = 4_000_000_000
LANE_SKEW_NS = 300_000_000
SEED = 20260727


@dataclass(frozen=True)
class Step:
    """One scheduled acquisition on one lane."""

    kind: int
    level: int = 0
    peak: int = DEFAULT_PEAK
    saturate: bool = False
    pileup: bool = False
    unstable: bool = False
    frozen_time: bool = False


@dataclass(frozen=True)
class LanePlan:
    """Physical description of one readout lane."""

    baseline: float
    gain: float
    drift: float
    pedestal_offset: float
    pedestal_drift: float


@dataclass(frozen=True)
class Entry:
    """One generated frame, kept addressable so duplicates can be injected."""

    lane_id: int
    acq_seq: int
    payload: bytes
    step: Step


@dataclass(frozen=True)
class Group:
    """One acquisition run written across several shards."""

    run_id: int
    adc_bits: int
    polarity: int
    lanes: dict[int, LanePlan]
    schedules: dict[int, list[Step]]
    shards: dict[str, int]
    lane_shard: dict[int, str]
    conflicts: list[tuple[int, int, str, float]] = field(default_factory=list)
    copies: list[tuple[int, int, str]] = field(default_factory=list)
    repeats: list[tuple[int, int, float]] = field(default_factory=list)


def pedestals(count: int, *, unstable: bool = False) -> list[Step]:
    """A block of ``count`` pedestal acquisitions."""
    return [Step(kind=KIND_PEDESTAL, unstable=unstable) for _ in range(count)]


def pulse(
    level: int,
    *,
    peak: int = DEFAULT_PEAK,
    saturate: bool = False,
    pileup: bool = False,
    frozen_time: bool = False,
) -> list[Step]:
    """A single pulser acquisition at ``level``."""
    return [
        Step(
            kind=KIND_PULSER,
            level=level,
            peak=peak,
            saturate=saturate,
            pileup=pileup,
            frozen_time=frozen_time,
        )
    ]


def _rails(adc_bits: int) -> tuple[int, int]:
    span = 1 << (adc_bits - 1)
    return -span, span - 1


def _triangle(index: int, center: float) -> float:
    return max(0.0, 1.0 - abs(index - center) / PULSE_WIDTH)


def _samples(
    plan: LanePlan,
    step: Step,
    *,
    lane_id: int,
    acq_seq: int,
    elapsed: float,
    polarity: int,
    adc_bits: int,
    pedestal_index: int,
    scale: float,
) -> list[int]:
    rail_low, rail_high = _rails(adc_bits)
    rng = random.Random(
        SEED
        + lane_id * 9_176_081
        + acq_seq * 7_919
        + step.kind * 131
        + int(scale * 1000) * 17
    )
    excursion = plan.pedestal_offset + plan.pedestal_drift * elapsed
    if step.unstable:
        excursion += UNSTABLE_SHIFT if pedestal_index % 2 == 0 else -UNSTABLE_SHIFT
    amplitude = 0.0
    if step.kind == KIND_PULSER:
        excursion += plan.drift * elapsed
        amplitude = step.level * plan.gain * scale

    values: list[int] = []
    for index in range(SAMPLE_COUNT):
        value = (
            plan.baseline
            + DITHER_AMPLITUDE * DITHER_PATTERN[index % 4]
            + rng.gauss(0.0, NOISE_SIGMA)
        )
        if index >= PRE_TRIGGER:
            shape = excursion
            if amplitude:
                shape += amplitude * _triangle(index, step.peak)
                if step.pileup:
                    shape += PILEUP_SCALE * amplitude * _triangle(
                        index, step.peak + PILEUP_OFFSET
                    )
            value += polarity * shape
        values.append(max(rail_low + 1, min(rail_high - 1, round(value))))

    if step.saturate:
        values[step.peak] = rail_high if polarity > 0 else rail_low
    return values


def _encode_frame(
    *,
    lane_id: int,
    step: Step,
    acq_seq: int,
    timestamp_ns: int,
    polarity: int,
    samples: list[int],
) -> bytes:
    payload = struct.pack(f"<{len(samples)}h", *samples)
    header = _FRAME_HEADER.pack(
        lane_id,
        step.kind,
        acq_seq,
        step.level,
        timestamp_ns,
        len(samples),
        polarity,
        zlib.crc32(payload) & 0xFFFFFFFF,
    )
    return header + payload


def _encode_shard(
    *,
    run_id: int,
    shard_index: int,
    adc_bits: int,
    frames: list[bytes],
) -> bytes:
    header = _FILE_HEADER.pack(
        MAGIC,
        VERSION,
        HEADER_BYTES,
        run_id,
        shard_index,
        adc_bits,
        len(frames),
        0,
    )
    return header + b"".join(frames)


def _timestamp(lane_id: int, position: int) -> int:
    return BASE_TIMESTAMP_NS + position * STEP_NS + lane_id * LANE_SKEW_NS


def _generate(group: Group, lane_id: int, scale: float = 1.0) -> list[Entry]:
    plan = group.lanes[lane_id]
    entries: list[Entry] = []
    pedestal_index = 0
    frozen: int | None = None
    for position, step in enumerate(group.schedules[lane_id]):
        acq_seq = position + 1
        timestamp_ns = _timestamp(lane_id, position)
        if step.frozen_time:
            frozen = timestamp_ns if frozen is None else frozen
            timestamp_ns = frozen
        elapsed = (timestamp_ns - BASE_TIMESTAMP_NS) / 1e9
        samples = _samples(
            plan,
            step,
            lane_id=lane_id,
            acq_seq=acq_seq,
            elapsed=elapsed,
            polarity=group.polarity,
            adc_bits=group.adc_bits,
            pedestal_index=pedestal_index,
            scale=scale,
        )
        if step.kind == KIND_PEDESTAL:
            pedestal_index += 1
        entries.append(
            Entry(
                lane_id=lane_id,
                acq_seq=acq_seq,
                payload=_encode_frame(
                    lane_id=lane_id,
                    step=step,
                    acq_seq=acq_seq,
                    timestamp_ns=timestamp_ns,
                    polarity=group.polarity,
                    samples=samples,
                ),
                step=step,
            )
        )
    return entries


def _build_group(group: Group) -> dict[str, list[bytes]]:
    generated = {lane_id: _generate(group, lane_id) for lane_id in group.schedules}
    altered: dict[tuple[int, float], list[Entry]] = {}
    for lane_id, _, _, scale in group.conflicts:
        key = (lane_id, scale)
        if key not in altered:
            altered[key] = _generate(group, lane_id, scale=scale)

    shard_frames: dict[str, list[bytes]] = {name: [] for name in group.shards}
    for lane_id, entries in sorted(generated.items()):
        target = shard_frames[group.lane_shard[lane_id]]
        target.extend(entry.payload for entry in entries)

    for lane_id, acq_seq, target, scale in group.conflicts:
        entry = next(
            item for item in altered[(lane_id, scale)] if item.acq_seq == acq_seq
        )
        shard_frames[target].append(entry.payload)
    for lane_id, acq_seq, target in group.copies:
        entry = next(item for item in generated[lane_id] if item.acq_seq == acq_seq)
        shard_frames[target].append(entry.payload)
    for lane_id, acq_seq, scale in group.repeats:
        repeated = _generate(group, lane_id, scale=scale)
        entry = next(item for item in repeated if item.acq_seq == acq_seq)
        shard_frames[group.lane_shard[lane_id]].append(entry.payload)
    return shard_frames


NIGHT = Group(
    run_id=4201,
    adc_bits=12,
    polarity=1,
    lanes={
        0: LanePlan(-300.0, 0.42, 0.055, 1.2, 0.005),
        1: LanePlan(-260.0, 0.30, 0.090, 1.0, 0.004),
        2: LanePlan(-220.0, 0.35, 0.030, 1.4, 0.006),
        3: LanePlan(-180.0, 0.25, 0.070, 0.9, 0.003),
        4: LanePlan(-140.0, 0.38, 0.040, 1.1, 0.007),
        5: LanePlan(-100.0, 0.20, 0.062, 1.3, 0.005),
    },
    schedules={
        0: [
            *pedestals(6),
            *pulse(500),
            *pulse(100),
            *pulse(800),
            *pedestals(1),
            *pulse(300),
            *pulse(700),
            *pulse(200),
            *pedestals(1),
            *pulse(600),
            *pulse(400),
        ],
        1: [
            *pulse(400),
            *pulse(700),
            *pedestals(5),
            *pulse(200),
            *pulse(800),
            *pulse(300),
            *pedestals(1),
            *pulse(600),
            *pulse(100),
            *pulse(500),
        ],
        2: [
            *pedestals(6),
            *pulse(600),
            *pulse(150),
            *pulse(450, pileup=True),
            *pulse(900),
            *pedestals(1),
            *pulse(300, pileup=True),
            *pulse(750),
            *pulse(250),
            *pulse(500),
        ],
        3: [
            *pedestals(6),
            *pulse(700, peak=92),
            *pulse(200, peak=92),
            *pulse(900, peak=94),
            *pulse(500, peak=92),
            *pedestals(1),
            *pulse(300, peak=94),
            *pulse(1000, peak=92),
            *pulse(400, peak=92),
            *pulse(600, peak=94),
            *pulse(800, peak=92),
        ],
        4: [
            *pedestals(6),
            *pulse(300),
            *pulse(600),
            *pulse(300),
            *pulse(600),
            *pulse(300),
            *pulse(600),
        ],
        5: [
            *pedestals(6),
            *pulse(600),
            *pulse(150),
            *pulse(1050, saturate=True),
            *pulse(300),
            *pulse(900),
            *pedestals(1),
            *pulse(450, saturate=True),
            *pulse(1200),
            *pulse(750),
        ],
    },
    shards={"night_z.pmw2": 0, "night_a.pmw2": 1, "night_m.pmw2": 2},
    lane_shard={
        0: "night_z.pmw2",
        1: "night_z.pmw2",
        2: "night_a.pmw2",
        3: "night_a.pmw2",
        4: "night_m.pmw2",
        5: "night_m.pmw2",
    },
    conflicts=[
        (0, 7, "night_a.pmw2", 0.55),
        (0, 8, "night_a.pmw2", 0.55),
        (0, 12, "night_a.pmw2", 1.40),
    ],
    copies=[
        (2, 1, "night_m.pmw2"),
        (2, 2, "night_m.pmw2"),
    ],
    repeats=[(4, 7, 0.6)],
)

CROSS = Group(
    run_id=4202,
    adc_bits=14,
    polarity=1,
    lanes={
        6: LanePlan(-520.0, 0.85, 0.075, 1.5, 0.006),
        7: LanePlan(-460.0, 0.62, 0.045, 1.1, 0.004),
        8: LanePlan(-400.0, 0.70, 0.050, 1.2, 0.005),
        9: LanePlan(-340.0, 0.54, 0.085, 1.6, 0.007),
        10: LanePlan(-280.0, 0.93, 0.035, 0.8, 0.003),
        11: LanePlan(-220.0, 0.48, 0.060, 1.3, 0.005),
    },
    schedules={
        6: [
            *pedestals(5),
            *pulse(600),
            *pulse(200),
            *pedestals(1),
            *pulse(900),
            *pulse(400),
            *pedestals(1),
            *pulse(700),
            *pulse(300),
            *pedestals(1),
            *pulse(800),
            *pulse(500),
        ],
        7: [
            *pedestals(4, unstable=True),
            *pulse(700),
            *pulse(300),
            *pedestals(4, unstable=True),
            *pulse(900),
            *pedestals(8),
            *pulse(1000),
            *pulse(400),
            *pulse(800),
            *pulse(200),
            *pulse(600),
            *pulse(500),
        ],
        8: [
            *pedestals(8, unstable=True),
            *pulse(400),
            *pulse(800),
            *pedestals(1, unstable=True),
            *pulse(200),
            *pedestals(1, unstable=True),
            *pulse(600),
        ],
        9: [
            *pulse(600),
            *pulse(200),
            *pulse(900),
            *pedestals(5),
            *pulse(1000),
            *pulse(300),
            *pulse(700),
            *pedestals(1),
            *pulse(400),
            *pulse(800),
            *pulse(500),
        ],
        10: [
            *pedestals(4),
            *pulse(600),
            *pedestals(1),
            *pulse(150),
            *pedestals(1),
            *pulse(900),
            *pedestals(1),
            *pulse(300),
            *pedestals(1),
            *pulse(1050),
            *pedestals(1),
            *pulse(450),
            *pulse(750),
        ],
        11: [*pedestals(6)],
    },
    shards={"cross_c.pmw2": 0, "cross_a.pmw2": 1, "cross_b.pmw2": 2},
    lane_shard={
        6: "cross_c.pmw2",
        7: "cross_c.pmw2",
        8: "cross_a.pmw2",
        9: "cross_a.pmw2",
        10: "cross_b.pmw2",
        11: "cross_b.pmw2",
    },
    conflicts=[
        (6, 6, "cross_a.pmw2", 0.60),
        (6, 9, "cross_a.pmw2", 0.60),
        (6, 13, "cross_b.pmw2", 1.35),
    ],
    copies=[
        (10, 1, "cross_a.pmw2"),
        (10, 2, "cross_a.pmw2"),
        (10, 3, "cross_c.pmw2"),
    ],
    repeats=[],
)

EDGE = Group(
    run_id=4203,
    adc_bits=12,
    polarity=-1,
    lanes={
        12: LanePlan(-90.0, 0.33, 0.058, 1.2, 0.006),
        13: LanePlan(-140.0, 0.26, 0.041, 1.0, 0.004),
        14: LanePlan(-190.0, 0.29, 0.066, 1.4, 0.005),
        15: LanePlan(-240.0, 0.37, 0.050, 0.9, 0.003),
    },
    schedules={
        12: [
            *pedestals(6),
            *pulse(500),
            *pulse(200),
            *pulse(800),
            *pedestals(1),
            *pulse(300),
            *pulse(700),
            *pulse(400),
            *pulse(600),
        ],
        13: [
            *pedestals(6),
            *pulse(700, peak=92),
            *pulse(300, peak=92),
            *pulse(900, peak=95),
            *pulse(1000, peak=92),
            *pedestals(1),
            *pulse(400, peak=93),
            *pulse(200, peak=92),
            *pulse(600, peak=94),
            *pulse(800, peak=92),
            *pulse(500, peak=92),
        ],
        14: [
            *pedestals(6),
            *pulse(600),
            *pulse(900, saturate=True),
            *pulse(300),
            *pulse(800),
            *pulse(400),
            *pedestals(1),
            *pulse(200, saturate=True),
            *pulse(700),
            *pulse(500),
        ],
        15: [
            *pedestals(6),
            *pulse(600, frozen_time=True),
            *pulse(300, frozen_time=True),
            *pulse(900, frozen_time=True),
            *pulse(600, frozen_time=True),
            *pulse(300, frozen_time=True),
            *pulse(900, frozen_time=True),
        ],
    },
    shards={"edge_b.pmw2": 0, "edge_a.pmw2": 1},
    lane_shard={
        12: "edge_b.pmw2",
        13: "edge_b.pmw2",
        14: "edge_a.pmw2",
        15: "edge_a.pmw2",
    },
    conflicts=[(12, 8, "edge_a.pmw2", 0.70)],
    copies=[],
    repeats=[],
)

GROUPS = (NIGHT, CROSS, EDGE)


def main() -> None:
    """Write every bundled shard, replacing any earlier copy."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for group in GROUPS:
        frames = _build_group(group)
        for basename, shard_index in group.shards.items():
            image = _encode_shard(
                run_id=group.run_id,
                shard_index=shard_index,
                adc_bits=group.adc_bits,
                frames=frames[basename],
            )
            (FIXTURES / basename).write_bytes(image)


if __name__ == "__main__":
    main()
