# Vaccine cold-chain deployment export contract

This contract defines vaccine cold-chain deployment exports for the bundle under `/app/environment`. Agents align observed export mismatches against these obligations. Policy values in `/app/environment/config/coldchain_policy.toml` must match this contract; the policy loader must honor those values at runtime; output-only edits are insufficient.

## Cold-chain policy precedence

File: `/app/environment/config/coldchain_policy.toml`

- `[lineage] parent_link_mode` — field must be `enforce_parent` so split children record the parent batch id; `omit_parent` drops lineage links
- `[lineage] child_id_mode` — field must be `increment_generation` so child ids use `{parent}-s{N}` with increasing split generation; `fixed_zero_suffix` always emits `-s0`
- `[recovery] temp_on_recovery` — field must be `preserve_transit` so recovered shipments keep transit temperature history; `reset_ok` clears violations on recovery
- `[merge] quarantine_mode` — field must be `honor_violation` so doses exposed above 8.0°C enter quarantined inventory; `ignore_violation` keeps them usable
- `[merge] in_transit_release` — field must be `release` so recovered merges keep the origin dispatch debit (doses stay removed from the origin batch); `skip` restores those doses on the origin and double-counts inventory against the destination

## Bundled runner

`/app/bin/vcs_sim run --scenario <scenario_id> [--rounds N]`

Working directory is `/app`. Outputs land under `/app/output/`. Checkpoint persists at `/app/environment/state/checkpoint.json`.

## Cold-chain threshold

Transit temperature readings above **8.0** degrees Celsius mark affected shipment doses as **quarantined** on delivery or recovery. Quarantined doses remain in inventory tallies but are excluded from **usable** counts.

## Batch lineage

Partial facility transfers split a parent batch into a child batch. The child batch id is `{parent_id}-s{split_gen}` where `split_gen` is one greater than the parent's current split generation (root batches use split generation 0). The child must record `parent_id` equal to the parent batch id and `split_gen` equal to its generation. The parent dose count decreases by the split amount.

## Recovery merge

When an interrupted shipment is recovered, doses arrive at the destination facility. Merge must first remove the in-transit hold for that shipment id, then add doses with status reflecting temperature history (quarantined when max transit reading exceeded 8.0). Recovered quarantined doses must not enter usable totals.

## Expiry

Batches whose `expires_day` is less than or equal to the current simulation round are **expired** and excluded from usable totals.

## inventory.json

Top-level fields: `schema_version` (1), `scenario_id`, `round`, `facilities` (map of facility id to object with `usable_doses`, `quarantined_doses`, `batches` array), `lineage` (array of `{batch_id, parent_id, split_gen, doses}`), `temperature_summary` (`max_reading_c`, `violations` count), `state_digest` (16 lowercase hex chars).

Facility batch entries include `batch_id`, `parent_id`, `split_gen`, `doses`, `status` (`usable`, `quarantined`, or `expired`).

## shipments.csv

Header: `round,shipment_id,origin,destination,batch_id,doses,status,temp_ok`

`status` is one of `in_transit`, `delivered`, `interrupted`, `recovered`, or `quarantined`. `temp_ok` is `true` or `false`.

## compliance.log

One event per line:

```
SEQ=<n> ROUND=<r> EVENT=<kind> <key=value pairs>
```

Kinds include `lineage`, `temp_check`, `delivery`, `recovery`, `expiry`. Lineage events include `PARENT`, `CHILD`, `SPLIT_GEN`, `DOSES`. Temp events include `SHIPMENT`, `READING_C`, `STATUS` (`ok` or `violation`).

## analytics.json

Fields: `total_usable_doses`, `total_quarantined_doses`, `total_shipped`, `total_delivered`, `state_digest`, `compliance_pass` (boolean).

Cross-format rules:

- `analytics.total_usable_doses` equals the sum of `facilities[*].usable_doses` in inventory.json.
- `analytics.total_quarantined_doses` equals the sum of `facilities[*].quarantined_doses`.
- `analytics.total_delivered` equals the count of CSV rows where `status` is `delivered` or `recovered` and `temp_ok` is `true`, summing `doses`.
- `analytics.state_digest` equals `inventory.state_digest`.
- `compliance_pass` is true only when `temperature_summary.violations` equals the number of compliance log lines with `STATUS=violation` and lineage child rows match inventory lineage.

## Checkpoint

`checkpoint.json` stores `round`, `scenario_id`, `facilities`, `shipments`, `lineage`, `temp_log`, and `seq`. Each successful run advances `round` and preserves cumulative history unless the scenario id changes (then state resets).

## State digest

Sort facility ids. For each facility, sort batch ids. Concatenate `facility_id|batch_id|doses|status` with `;` between batches and `||` between facilities. SHA-256 the string, take first 16 hex digits.

## Negative paths

- Expired batches: status `expired`, excluded from usable.
- Cold-chain failure: temp_ok false, doses quarantined.
- Delivery interruption: status `interrupted` until recovery round.
- Partial recovery: only recovered shipment doses merge; in-transit hold cleared once.
- Invalid manifests: shipments referencing unknown batch ids are skipped and logged with EVENT=skip.
