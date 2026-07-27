# Wakeclock systemd timer administration contract

`wakeclock reconcile` is the local timer-unit administrator for this environment. It manages persistent `.timer.json` unit files, durable logical-clock traces, administration snapshots, journal records, and spool files in the style of systemd timer reconciliation; it must not read the host wall clock. All JSON objects reject unknown members. Times are RFC 3339 UTC values. Every successful JSON file uses the member order shown by the schemas below, two-space indentation, UTF-8, and one final newline. Journal records are compact JSON, one record per line. Unit filenames end in `.timer.json`; file order has no semantic meaning.

## Units and clock trace

A unit is `wakeclock.unit.v1` with, in order, `schema_version`, `unit_id`, `timezone`, `hour`, `minute`, `weekdays`, `persistent`, `random_delay_sec`, `accuracy_sec`, `depends_on`, `priority`, `enabled`, `catch_up_cap`, and `salt`. `timezone` is an IANA zone, weekdays are numbered with `0` for Sunday through `6` for Saturday, delay and accuracy are nonnegative seconds, and the catch-up cap is positive. Unit IDs and dependency entries are unique. Every dependency names another unit, and the complete dependency graph is acyclic.

The trace is JSONL. Each record has `seq`, `kind`, `utc`, and, for `boot`, `boot_id`. Sequence numbers are strictly increasing. Kinds are `boot`, `advance`, and `set`. `set` may move the current logical clock backward, but the durable high-water mark never decreases. A forward extension enumerates each UTC minute after the old high-water mark through the new instant, converts it through the unit's zone, and matches the resulting local weekday, hour, and minute. This UTC-first rule naturally creates two occurrences during a civil-time fold and none during a gap. A nonpersistent unit is eligible only when its scheduled UTC equals the trace event's UTC.

For a matched local minute, `scheduled_local` is `YYYY-MM-DDTHH:MM:SS`; `scheduled_utc` is canonical UTC RFC 3339; and `offset_sec` is the zone offset east of UTC. The occurrence ID is exactly

```
unit_id|scheduled_local|offset_sec|scheduled_utc
```

This canonical occurrence ID is used everywhere an occurrence is referenced: pending entries, journal occurrence arrays, spool occurrence arrays, activation reports, coalescing groups, skipped records, dependency decisions, and cursors. A legacy two-part value such as `unit_id|scheduled_local` is not equivalent and is invalid wherever a canonical occurrence ID is required.

The deterministic delay seed is the UTF-8 text `unit_id + "\n" + occurrence_id + "\n" + salt + "\n"`. Interpret the first eight SHA-256 bytes as an unsigned big-endian integer and take it modulo `random_delay_sec + 1`. `delayed_utc` is `scheduled_utc` plus that many seconds. Delay does not depend on enumeration order or unrelated units.

## Pending work, coalescing, and dependencies

The snapshot is `wakeclock.state.v1` with `schema_version`, `trace_seq`, `clock_utc`, `high_water_utc`, `boot_id`, `pending`, `committed_ids`, `last_activation`, and `cursors`. Pending entries carry `unit_id`, `occurrence_id`, `scheduled_local`, `scheduled_utc`, `offset_sec`, `delayed_utc`, `accuracy_sec`, `priority`, and `depends_on`. Each unit retains at most its `catch_up_cap` newest scheduled pending occurrences; older excess entries are skipped with `dependency_decisions[].decision = "skipped_catch_up_cap"` and `skipped[].reason = "catch_up_cap"`. Backward clock movement neither re-enumerates nor discards pending work.

An occurrence becomes ready when `delayed_utc <= clock_utc`. Sort ready occurrences by delayed UTC, then unit ID, then occurrence ID. Its accuracy window is the closed interval from delayed UTC through delayed UTC plus accuracy seconds. Form each coalescing group as the maximal consecutive set with a nonempty intersection: initialize the deadline from the first window, accept the next occurrence when its delayed UTC is no later than the current deadline, and reduce the deadline to the earlier window end. Coalescing therefore occurs after deterministic delay and is independent of input file order.

Dependency classification is performed against the final group produced from delayed-time accuracy-window intersection, not scheduled-time adjacency. Within that group, a dependency that is also present must run first. A dependency absent from the group is satisfied only when `last_activation` contains a nonempty value for it. Missing prerequisites skip the affected occurrence with `dependency_decisions[].decision = "skipped_missing_prerequisite"` and `skipped[].reason = "missing_prerequisite"`; dependents of a skipped same-group occurrence are also skipped. Among currently eligible occurrences, higher priority runs first, then lexicographically smaller unit ID.

Each dispatchable occurrence is reported once in `dependency_decisions` with exactly one of these decision strings:

- `ready`: the occurrence has no dependencies.
- `ordered_after_group_dependency`: at least one dependency occurrence is present in the same final coalescing group and the occurrence is dispatchable after those dependencies.
- `satisfied_by_history`: the occurrence has dependencies, none is present in the same group, and every dependency has a nonempty `last_activation` entry.
- `skipped_missing_prerequisite`: at least one dependency is absent from the group without valid history, or a required same-group dependency was skipped.

When an occurrence has both same-group and historical dependencies, use `ordered_after_group_dependency` after all prerequisites are satisfied.

The coalescing group ID is lowercase SHA-256 of the group's occurrence IDs sorted lexicographically and joined with `\n` without a trailing delimiter. The activation ID is lowercase SHA-256 of `"activation\n" + group_id + "\n"`. The effective time is the earliest delayed UTC in the group. An activation's unit and occurrence arrays follow dependency dispatch order; the journal and coalescing record retain the sorted full group occurrence IDs.

## Journal, spool, and recovery

Timer dispatch durability follows a three-phase journal protocol analogous to systemd unit activation bookkeeping. Dispatch durability uses `prepare`, `spool`, and `commit` journal records, in that order, with identical activation ID, group ID, and sorted occurrence IDs. The spool file is `state/spool/<activation_id>.json` and contains the activation object. A committed activation is added to `committed_ids`, removes its occurrences from pending, advances unit cursors, and updates `last_activation` for activated units.

At startup, a prepare without a spool record or file is discarded from the journal and left pending for normal retry (`discarded_prepare`). A prepare plus spool record and valid spool file without commit is completed by appending commit and applying its state effects (`completed_spool`). A complete journal activation missing from the snapshot is applied (`replayed_commit`). Already committed complete activations are unchanged. Phase order errors, mismatched identity fields, missing or unexpected spool files, or committed IDs without complete journal evidence are invalid.

## Report

The output is `wakeclock.reconcile.v1` with, in order, `schema_version`, `trace_seq`, `recovered`, `activations`, `skipped`, `coalescing_groups`, `dependency_decisions`, `final_cursors`, and `state_digest`. Arrays are present even when empty. `state_digest` is lowercase SHA-256 of the compact JSON serialization of the final snapshot using the snapshot's documented member order. A completed rerun with the same durable inputs produces no new activations or journal records and leaves the snapshot stable.
