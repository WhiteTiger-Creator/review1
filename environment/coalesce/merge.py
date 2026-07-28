"""Shard-set consistency and acquisition-identity merge."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pmwio.decoder import ShardRecord, WaveFrame


@dataclass(frozen=True)
class MergeStats:
    frames_read: int
    frames_rejected_duplicate: int
    frames_conflicting: int


def validate_shard_set(shards: Sequence[ShardRecord]) -> tuple[int, int]:
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
    retained: dict[tuple[int, int], WaveFrame] = {}
    frames_read = 0
    duplicates = 0
    conflicting = 0

    for shard in sorted(shards, key=lambda record: record.basename):
        for frame in shard.frames:
            frames_read += 1
            key = (frame.lane_id, frame.acq_seq)
            kept = retained.get(key)
            if kept is None:
                retained[key] = frame
                continue
            duplicates += 1
            if kept.content != frame.content:
                conflicting += 1

    def process_order(frame: WaveFrame) -> tuple[int, int, int, int]:
        return (frame.timestamp_ns, -frame.kind, frame.lane_id, frame.acq_seq)

    ordered = sorted(retained.values(), key=process_order)
    stats = MergeStats(
        frames_read=frames_read,
        frames_rejected_duplicate=duplicates,
        frames_conflicting=conflicting,
    )
    return ordered, stats
