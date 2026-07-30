# Hall certification replay contract

The programme office replays each published hall through the controller and
publishes one JSON document. The document carries:

- `schema_version` (unsigned integer, currently 1)
- `sites` (array of per-hall rows)
- `program_attestation` (64-character lowercase hex SHA-256 over the sorted
  per-hall attestations joined with `|`)

Each hall row carries:

- `name` — hall identifier taken from the published site index
- `rack_count` — racks ingested from the hall inventory
- `certified_count` — racks that survive every certification stage
- `compute_blocks` — racks held for insufficient ready nodes or a firmware
  revision outside the permitted set
- `storage_blocks` — racks held for insufficient usable capacity or too few
  replica copies
- `network_blocks` — racks held for too few healthy uplinks at or above the
  required line rate
- `approval_blocks` — racks held for missing quorum among distinct unexpired
  approver roles, or for a missing mandatory role
- `maintenance_blocks` — racks held for an unresolved service record or one
  still inside the cool-down span
- `region_rejections` — racks rejected because their hardware class is not
  permitted for the hall
- `capacity_trims` — racks trimmed when the hall power draw ceiling is reached
- `readiness_index` — sum over certified racks of rack tier multiplied by the
  weight configured for that rack's region
- `attestation` — 64-character lowercase hex SHA-256 over the canonical stats
  payload described in `attestation_rules.md`

## Certification policy

No single subsystem certifies a rack. A rack is certified only when it clears
every stage the controller applies, and the stages consume shared hall policy:
node floors, permitted firmware revisions, usable-capacity and replica floors,
uplink line rate and redundancy, approver quorum and mandatory roles, service
cool-down spans, permitted hardware classes, region weights, and the hall power
draw ceiling. The stages run in sequence, a rack removed by an earlier stage is
never counted by a later one, and each counter reports only the racks that
stage removed.

Every rack is therefore accounted for exactly once. Writing `removed` for the
sum of the seven removal counters, each published row satisfies:

```
certified_count + removed == rack_count
```

Approvals are evaluated against the hall evaluation epoch: an approval whose
expiry is at or before that epoch does not count, and repeated approvals from
the same role count once.

Service records are evaluated per rack against the most recent record on file.

Power fitting walks the surviving racks in descending tier, breaking ties by
ascending rack identifier. A rack is admitted when its draw fits in the
remaining hall ceiling; otherwise it is trimmed and the walk continues with the
next rack.

Ordering and tie-breaking must stay deterministic across replays. Regenerate
only through the controller binary; static JSON writes are rejected.
