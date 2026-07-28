# NFS Export ACL Operations Policy

## 1. Purpose

The systemd oneshot `/app/systemd/nfs-export-acld.service` converges NFS export ACL inventory after a storage service restart by replaying the on-disk journal under `/app/var/lib/nfs-acld/`. Operators must ensure the unit leaves live export grants and compliance metrics under the configured runtime directory so revoke cascades, waitlist promotions, and secure-port sticky enforcement can be validated. Replay must be idempotent with respect to `op_id`.

## 2. Configuration

Base configuration is `/app/config/exports.json`.

| Field | Meaning |
|-------|---------|
| `export_table_id` | Identifier for the managed NFS export table |
| `max_clients_per_export` | Maximum simultaneous client grants per export path |
| `default_squash` | Squash mode used when a grant omits `squash` (`no_root_squash`, `root_squash`, or `all_squash`) |
| `default_anon_uid` | Anonymous UID used when a grant omits `anon_uid`, and when `all_squash` is applied |
| `default_anon_gid` | Anonymous GID used when a grant omits `anon_gid`, and when `all_squash` is applied |
| `default_access` | Access mode used when a grant omits `access` (`ro` or `rw`) |
| `require_secure_ports` | When true, grants with `secure=false` are labeled `insecure` |
| `evaluation_clock` | Integer clock recorded into runtime state (no time-window math beyond journal `ts`) |
| `profile` | Profile name used only for optional overlay discovery |
| `journal_path` | Absolute path to the JSONL journal |
| `output_dir` | Absolute directory for persisted runtime state |

`max_clients_per_export`, `default_squash`, `default_anon_uid`, `default_anon_gid`, `default_access`, and `require_secure_ports` in the base configuration are authoritative. Profile overlay files under `/app/config/profiles/` may exist for site discovery, but must not alter those fields, `export_table_id`, or `evaluation_clock`. Persisted runtime state must not be re-aligned afterward using overlay max-clients, governance baseline values, or any other secondary source.

## 3. Client Specificity

Each client grant carries a `specificity` integer used only for ordering:

- Hostname clients (any `client_id` containing a letter `a-z` or `A-Z`): specificity `128`
- IPv4 CIDR clients (`A.B.C.D/P`): specificity `P`
- Bare IPv4 clients (`A.B.C.D` with no slash): specificity `32`

Within an export, clients sort by `specificity` descending, then `client_id` ascending.

## 4. Journal Format

Each journal line is one JSON object:

```json
{"op_id":"op01","ts":1000,"type":"create_export","export_path":"/srv/share/a"}
```

Fields:
- `op_id` (string, required): unique operation identifier
- `ts` (integer, required): operation timestamp
- `type` (string, required): one of `create_export`, `grant`, `revoke`, `enqueue`, `set_squash`, `set_access`, `destroy_export`, `reexport_pass`
- `export_path` (string): required for all types except `reexport_pass`
- `client_id` (string): required for grant/revoke/enqueue/set_squash/set_access
- `access` (string, optional): `ro` or `rw` for grant/set_access
- `squash` (string, optional): squash mode for grant/set_squash
- `anon_uid` / `anon_gid` (integer, optional): anon mapping for grant
- `secure` (boolean, optional): secure-port sticky flag for grant; default `true` when omitted

Operations are applied in file order. File order is already sorted by `(ts, op_id)`.

## 5. Idempotent Replay

If an `op_id` has already been applied, the duplicate line is skipped entirely and counted in `journal_skipped_dup`. Each first-seen `op_id` that is processed increments `journal_applied` by one. Replaying the same journal twice against an empty table must yield identical runtime state.

## 6. Create Export

1. If `export_path` already exists, no-op.
2. Create the export with an empty client set.

## 7. Grant

If the export does not exist, no-op. Otherwise:

1. If `client_id` is already granted on that export, no-op (do not rewrite options).
2. If the export already has `max_clients_per_export` grants, no-op.
3. Otherwise create the grant:
   - `access` from the operation when present, else base `default_access`
   - `squash` from the operation when present, else base `default_squash`
   - `anon_uid` / `anon_gid` from the operation when present, else base defaults
   - `secure` from the operation when present, else `true`
   - If resulting `squash` is `all_squash`, force `anon_uid` and `anon_gid` to the live base defaults held by the manager (not process-start captures and not overlay/governance values)
4. Compute `specificity` per §3.
5. `state` is `"insecure"` when `require_secure_ports` is true and `secure` is false; otherwise `"active"`.

Grant never mutates the waitlist.

## 8. Revoke

If the export or client grant does not exist, no-op. Otherwise remove the grant, then attempt waitlist promotion for that export path (see §11).

## 9. Enqueue

Append `{export_path, client_id}` to the FIFO waitlist when that exact pair is not already present. Enqueue never mutates grants. Waitlist order is strictly oldest-first: the head is always the earliest remaining reservation.

## 10. Set Squash / Set Access

If the export or client grant does not exist, no-op.

`set_squash`:
1. Update `squash` to the operation value.
2. When the new squash is `all_squash`, set `anon_uid` and `anon_gid` to the live base defaults held by the manager.
3. Recompute `state` from `secure` and `require_secure_ports` (squash changes do not clear insecure labeling).

`set_access`: update `access` only.

## 11. Waitlist Promotion

Promotion runs after `revoke` for the revoked export path, and during `reexport_pass` for every export with free capacity.

To promote one slot on `export_path`:
1. Scan the waitlist from the head and select the first entry whose `export_path` matches.
2. If none match, stop.
3. If the export is missing, dequeue that waitlist entry and stop (do not search further in this promote call).
4. If the export is already at `max_clients_per_export`, leave the entry on the waitlist and stop.
5. If `client_id` is already granted on the export, dequeue and stop.
6. Otherwise grant using base defaults (`default_access`, `default_squash`, `default_anon_uid`, `default_anon_gid`, `secure=true`), dequeue the entry, and stop.

A single promote call grants at most one client. Defaults come from the live manager values from base configuration, not from process-start captures, overlay files, or governance baselines.

## 12. Destroy Export

Remove the export and all of its client grants immediately. Destroy does **not** promote the waitlist.

## 13. Reexport Pass

At operation timestamp `ts` (recorded only for journaling), for each export path sorted ascending:
1. While the export has free client slots (`len(clients) < max_clients_per_export`) and the waitlist contains at least one matching `export_path` entry that can be promoted under §11, run one promote call.
2. Stop the inner loop when a promote call does not dequeue an entry, or when capacity is full.

## 14. Persisted Runtime State

Persist exactly two files under `output_dir`:

### `/app/run/export_acls.json`

```json
{
  "evaluation_clock": 0,
  "export_table_id": "string",
  "max_clients_per_export": 0,
  "exports": [
    {
      "export_path": "string",
      "clients": [
        {
          "client_id": "string",
          "access": "ro",
          "squash": "root_squash",
          "anon_uid": 0,
          "anon_gid": 0,
          "secure": true,
          "specificity": 0,
          "state": "active"
        }
      ]
    }
  ],
  "waitlist": [
    {"export_path": "string", "client_id": "string"}
  ]
}
```

`exports` must be sorted by `export_path` ascending. Each export's `clients` must be sorted by `specificity` descending, then `client_id` ascending. `waitlist` is the remaining FIFO queue. Numeric fields must reflect the replayed journal and base configuration. `max_clients_per_export` in this file must equal the base configuration value.

### `/app/run/export_metrics.json`

```json
{
  "export_count": 0,
  "client_grant_count": 0,
  "waitlist_depth": 0,
  "insecure_grant_count": 0,
  "over_capacity_exports": 0,
  "journal_applied": 0,
  "journal_skipped_dup": 0,
  "slot_utilization_ratio": 0.0,
  "export_compliance": 0.0
}
```

Definitions:
- `export_count` = number of exports
- `client_grant_count` = total client grants across all exports
- `waitlist_depth` = length of the remaining waitlist
- `insecure_grant_count` = number of grants with `state == "insecure"`
- `over_capacity_exports` = number of exports with more grants than base `max_clients_per_export`
- `slot_utilization_ratio` = `0` when `export_count == 0`; otherwise `round(client_grant_count / (export_count * max_clients_per_export), 4)` using half-away-from-zero rounding to 4 decimal places
- `export_compliance` = `max(0, round(100 - penalties, 2))` where penalties accumulate as:
  - `+20` per insecure grant
  - `+25` per over-capacity export
  - `+2` per waitlist entry

## 15. Invariants

- Duplicate `op_id` lines never mutate state.
- Base configuration controls max clients, squash/access/anon defaults, and secure-port enforcement.
- Waitlist is FIFO; newer enqueues append and do not preempt.
- Waitlist promotion occurs only after revoke and during reexport passes.
- Destroy never promotes the waitlist.
- Create of an already-known `export_path` is a no-op.
- Grant of an already-known `(export_path, client_id)` is a no-op and does not rewrite options.
- Grant that would exceed `max_clients_per_export` is a no-op.
- Enqueue of an already-present waitlist pair is a no-op.
- `all_squash` forces anon UID/GID to live base defaults.
- Client ordering uses specificity descending, then `client_id` ascending.
- Final persisted `max_clients_per_export` and compliance math must use the same base max-clients value journal replay used; emit/persist must not substitute overlay or baseline max-clients.
- `slot_utilization_ratio` must use half-away-from-zero rounding to 4 decimal places (not truncation).
- Operations targeting unknown exports or unknown grants are no-ops.
- Default access/squash/anon values for grant and promote come from the live manager values held from base configuration, not from process-start captures.
