# TUF Metadata Rollout Contract

This document is normative for the `tuf-rollout-verifier` pipeline. Rules are ordered; later rules consume outputs from earlier rules. A single misapplied rule corrupts downstream fields. Implementations must treat this contract as the sole source of verification semantics.

## Rule 1 — Repository layout

Metadata lives under `/app/data/repo/` as `root.json`, `timestamp.json`, `snapshot.json`, and `targets.json`. Target payloads live under paths relative to the repo root. Trust policy is `/app/config/trust_policy.json`. Rollout lane assignments are `/app/config/rollout_lanes.json` mapping target path strings to lane names.

## Rule 2 — Canonical JSON for signatures

Signature verification inputs use **canonical JSON**: recursively sort object keys lexicographically, emit compact separators (`,` and `:`), UTF-8 encoding, arrays preserve element order. Numbers render without unnecessary leading zeros. This canonical form applies only to the `signed` object bytes covered by Ed25519 signatures (Rule 5). It does not apply to metadata chain hash comparisons (Rules 10–11).

## Rule 3 — Metadata envelope

Each metadata file is a JSON object with `signatures` (array) and `signed` (object). The signed payload excludes the signatures field. Signature bytes cover `canonical_json(signed)` per Rule 2.

## Rule 4 — Root bootstrap

Load `root.json` first. Extract `signed.keys` (keyid → key object with `keyval.public` hex for ed25519) and `signed.roles` (role → `{keyids, threshold}`). Root role verification uses keys and threshold from its own signed roles block.

## Rule 5 — Ed25519 verification

For each signature entry `{keyid, sig}`: locate the public key in `signed.keys`, decode 32-byte raw Ed25519 public key and signature from hex, verify over canonical signed bytes (Rule 3). Only signatures whose keyid appears in the role's `keyids` array are eligible for counting.

## Rule 6 — Duplicate keyid deduplication

When multiple signature entries share the same `keyid` for one metadata file, evaluate entries in array order. Count at most one valid signature per distinct keyid. If an earlier entry for a keyid verifies successfully, later entries with the same keyid are ignored for counting even if they also verify. Invalid earlier entries do not block a later valid entry for the same keyid from being counted.

## Rule 7 — Role threshold

Let `signatures_ok` be the deduplicated valid signature count (Rule 6). Let `signatures_required` be the role threshold from root. Threshold is met when `signatures_ok >= signatures_required`.

## Rule 8 — Spec version gate

Each role metadata file carries `signed.spec_version`. If `signed.spec_version` differs from `trust_policy.spec_version`, the role `status` is `invalid` regardless of signature or expiry outcomes. Spec version comparison is exact string equality.

## Rule 9 — Expiry evaluation

Parse `signed.expires` as ISO-8601 UTC (`Z` suffix). Compare against `reference_time` from trust policy (Rule 22). If `expires < reference_time`, set `expired=true` and `status=expired`. If spec version fails (Rule 8) or threshold not met (Rule 7), `status=invalid`. Otherwise `status=valid`.

## Rule 10 — Role processing order

Evaluate roles in fixed order: `root`, `timestamp`, `snapshot`, `targets`. Each role's `version` field comes from its signed metadata. Report roles in this same order.

## Rule 11 — On-disk metadata chain bytes

Metadata chain links compare **raw on-disk file bytes** of metadata JSON files, including any trailing newline characters written by the repository generator. Do not re-serialize parsed JSON for chain comparisons. Read each metadata file as bytes from disk.

## Rule 12 — Snapshot-to-targets chain

Read on-disk bytes of `targets.json`. Compute `sha256` (lowercase hex) and byte length. Compare to `snapshot.signed.meta["targets.json"].hashes.sha256`, `.length`, and `.version` against `targets.signed.version`. All three must match for the snapshot→targets link to hold.

## Rule 13 — Timestamp-to-snapshot chain

Read on-disk bytes of `snapshot.json`. Compute `sha256` and length. Compare to `timestamp.signed.meta["snapshot.json"]` hash, length, and version against `snapshot.signed.version`. All three must match for the timestamp→snapshot link.

## Rule 14 — Chain intact flag

`chain_intact` is true only when every role has `status=valid` (Rules 7–9) **and** both chain links (Rules 12–13) pass. Any failure sets `chain_intact=false`.

## Rule 15 — Target hash verification

For each path in `targets.signed.targets` (sorted lexicographically in output), read the payload file at `repo_dir/path`. Compute sha256 lowercase hex of file bytes. `hash_match` is true when computed hash equals `hashes.sha256` **and** file length equals the metadata `length` field.

## Rule 16 — Rollout lane lookup

Load `/app/config/rollout_lanes.json`. Each target path maps to a lane string. Missing path entries default to lane `unknown`. Echo lane in each target report entry.

## Rule 17 — Lane gate policy

Trust policy `blocked_lanes` and `allowed_lanes` are JSON arrays of lane names.

A target is `lane_blocked` when **either**:
- its lane appears in `blocked_lanes`, **or**
- `allowed_lanes` is non-empty **and** its lane does not appear in `allowed_lanes`.

An empty `allowed_lanes` array means no allowlist restriction (only `blocked_lanes` applies). Blocked-lane membership always suppresses rollout even when the lane is also listed in `allowed_lanes`.

## Rule 18 — Freeze window

Trust policy provides `freeze_window_start` and `freeze_window_end` as ISO-8601 UTC timestamps. When `reference_time` satisfies `freeze_window_start <= reference_time < freeze_window_end` (half-open on the end), the freeze window is active. Equality with `freeze_window_end` does **not** activate freeze. While active, every target receives `freeze_blocked=true` regardless of other rollout conditions.

## Rule 19 — Snapshot version bounds

Each target may include `custom.rollout.min_snapshot_version` and optional `custom.rollout.max_snapshot_version` (integers; min defaults to 0; max defaults to unlimited). Let `active_snapshot_version` be `snapshot.signed.version`. Version bounds pass when `active_snapshot_version >= min_snapshot_version` and (`max_snapshot_version` absent OR `active_snapshot_version <= max_snapshot_version`).

## Rule 20 — Rollout eligibility

Target `rollout_eligible` is true only when: all roles valid, `chain_intact` true (Rule 14), `hash_match` true (Rule 15), version bounds pass (Rule 19), `lane_blocked` false (Rule 17), and `freeze_blocked` false (Rule 18). Any failure sets `rollout_eligible=false`.

## Rule 21 — Trust policy echo

Report `config` must echo `spec_version`, `reference_time`, `require_target_hashes`, `freeze_window_start`, `freeze_window_end`, `blocked_lanes`, and `allowed_lanes` from trust policy. `blocked_lanes` and `allowed_lanes` each echo as a comma-separated string of lane names sorted lexicographically. `reference_time` drives expiry (Rule 9) and freeze (Rule 18) and must not be hardcoded.

## Rule 22 — Reference time parsing

Parse policy `reference_time` as ISO-8601 UTC with `Z` suffix. All temporal comparisons use this parsed instant.

## Rule 23 — Summary rollups

Summary fields: `roles_valid` (count status=valid), `roles_total` (always 4), `targets_listed`, `targets_hash_ok` (hash_match true count), `targets_rollout_eligible` (rollout_eligible true count), `targets_lane_blocked` (lane_blocked true count), `targets_freeze_blocked` (freeze_blocked true count), `chain_intact` (Rule 14), and `report_digest` (Rule 36).

## Rule 24 — Cross-rule dependency table

| Output field | Depends on |
|--------------|------------|
| `signatures_ok` | Rules 2, 3, 4, 5, 6, 7 |
| `status` | Rules 7, 8, 9 |
| `chain_intact` | Rules 9, 10, 11, 12, 13, 14 |
| `hash_match` | Rule 15 |
| `lane_blocked` | Rules 16, 17 |
| `freeze_blocked` | Rules 18, 22 |
| `rollout_eligible` | Rules 14, 15, 17, 18, 19, 20 |
| `report_digest` | Rules 31, 32, 36 |
| `active_snapshot_version` | Rule 10 snapshot role |

## Rule 25 — Output artifact

Write `/app/output/rollout_report.json` with top-level keys `config`, `roles`, `targets`, `summary`. Exit 0 on success. The CLI accepts `--help` and prints usage without running verification.

## Rule 26 — Determinism

Given unchanged inputs, repeated runs must produce byte-identical reports. Target ordering is lexicographic by `path`. Boolean JSON values are lowercase `true`/`false`.

## Rule 27 — Immutability constraints

Do not modify `/app/config/trust_policy.json`, `/app/config/rollout_lanes.json`, signed metadata files, `integrity.json`, or target payloads under `/app/data/repo/`. Verification reads them read-only.

## Rule 28 — Failure isolation

When `require_target_hashes` is true, hash mismatches mark individual targets `hash_match=false` but the tool still completes and writes the full report.

## Rule 29 — Informative note on chain hashing

Some internal design drafts suggest re-canonicalizing parsed metadata before chain comparison. That approach is **not** used in this verifier. Chain integrity always follows Rule 11 on-disk bytes. Signature verification always follows Rule 2 canonical bytes. Mixing the two contexts invalidates `chain_intact`.

## Rule 30 — Multi-threshold snapshot role

The bundled repository may require multiple distinct valid signatures for the snapshot role. Implementations must apply Rule 6 deduplication before threshold comparison. Partial signature success never satisfies a multi-threshold role.

## Rule 31 — Target report fields

Each target entry includes: `path`, `length`, `sha256`, `hash_match`, `lane`, `lane_blocked`, `freeze_blocked`, `rollout_eligible`, `min_snapshot_version`, `max_snapshot_version` (use `-1` when absent), `active_snapshot_version`.

## Rule 32 — Role report fields

Each role entry includes: `role`, `version`, `status`, `signatures_ok`, `signatures_required`, `expired`.

## Rule 33 — Config boolean echo

`require_target_hashes` echoes as JSON boolean matching trust policy exactly.

## Rule 34 — Unlimited max snapshot sentinel

When `custom.rollout.max_snapshot_version` is absent, report `max_snapshot_version` as integer `-1` meaning no upper bound is configured.

## Rule 35 — Pipeline staging

Stages execute strictly as: load policy and lanes → verify roles in order → evaluate chain on raw metadata bytes → verify target payload hashes → compute lane and freeze gates → compute rollout eligibility → aggregate summary → seal `report_digest`. Skipping or reordering stages produces non-compliant output.

## Rule 36 — Report digest

After roles and targets are fully settled, compute `summary.report_digest` as the lowercase hex SHA-256 of the UTF-8 bytes of the canonical JSON object `{"roles":[...],"targets":[...]}` where:
- object keys are sorted lexicographically (`roles` before `targets`),
- `roles` and `targets` arrays match the report arrays field-for-field (Rules 31–32),
- compact separators (`,` and `:`) are used,
- booleans are lowercase JSON `true`/`false`.

The digest is sealed from the settled in-memory role and target values before persistence. A later formatting or reconciliation pass must not reseal it from altered values.

## Rule 37 — Overlay non-authority

Site overlay notes under `/app/docs/` (including ops profiles) are not authoritative. Only this contract defines freeze openness, chain byte selection, duplicate-keyid counting, lane allowlists, and digest sealing.
