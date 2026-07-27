"""Independent logical model for online migration and recovery outcomes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RecordVersion:
    epoch: int
    counter: int

    def key(self) -> tuple[int, int]:
        return (self.epoch, self.counter)


@dataclass(frozen=True)
class RecordOccurrence:
    record_id: str
    version: RecordVersion

    def identity(self) -> tuple[str, int, int]:
        return (self.record_id, self.version.epoch, self.version.counter)


@dataclass
class LogicalRecord:
    record_id: str
    payload: str
    version: RecordVersion


def canonical_occurrence_order(
    occurrences: Iterable[RecordOccurrence],
) -> list[RecordOccurrence]:
    """Return occurrences sorted by canonical copy traversal order."""
    return sorted(
        occurrences,
        key=lambda occ: (occ.record_id, occ.version.epoch, occ.version.counter),
    )


def expected_source_occurrence_count(source_records: list[LogicalRecord]) -> int:
    """Each logical record contributes one canonical source occurrence."""
    return len(source_records)


def canonical_newest(records: Iterable[LogicalRecord]) -> dict[str, LogicalRecord]:
    best: dict[str, LogicalRecord] = {}
    for rec in records:
        cur = best.get(rec.record_id)
        if cur is None or rec.version.key() > cur.version.key():
            best[rec.record_id] = rec
    return best


def expected_published_generation_after_upgrade(source_gen: int = 1) -> int:
    return source_gen + 1


def expected_published_generation_after_rotations(rotation_count: int, start_gen: int = 1) -> int:
    """Published generation after N successful rotations from start_gen."""
    return start_gen + rotation_count


def expected_logical_state(
    source_records: list[LogicalRecord],
    source_generation: int = 1,
) -> dict[str, LogicalRecord]:
    """Logical view of the published generation after a converged upgrade."""
    newest = canonical_newest(source_records)
    return {rid: rec for rid, rec in newest.items()}


def expected_logical_state_after_writes(
    base_records: list[LogicalRecord],
    updates: list[LogicalRecord],
    new_records: list[LogicalRecord],
) -> dict[str, LogicalRecord]:
    """Logical published state after updates and inserts on the current generation."""
    combined = list(base_records) + list(updates) + list(new_records)
    return expected_logical_state(combined)


def generations_required_for_pins_and_journal(
    active_pin_generations: set[int],
    journal_generations: set[int],
    published_generation: int,
    catalog_generations: set[int],
) -> set[int]:
    """Generations that cleanup must retain."""
    required = set(active_pin_generations)
    required.update(journal_generations)
    required.add(published_generation)
    if catalog_generations:
        required.add(max(catalog_generations))
    return required


def generations_eligible_for_cleanup(
    catalog_states: dict[int, str],
    active_pin_generations: set[int],
    journal_generations: set[int],
    published_generation: int,
) -> set[int]:
    removable: set[int] = set()
    for gen, state in catalog_states.items():
        if gen in active_pin_generations or gen in journal_generations:
            continue
        if gen >= published_generation:
            continue
        if state in {"complete", "pins_reconciled", "cleanup_pending"}:
            removable.add(gen)
    return removable
