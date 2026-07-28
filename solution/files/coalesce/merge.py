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
