# Recovery output contract

All TSV files use a single tab between fields, one header row, one data row per record, and a final newline. Do not quote or escape fields. Integer fields use base-10 digits with no padding. Empty values are represented by adjacent tab separators; do not write `null`, `NA`, or other placeholders.

## TSV outputs

### `/app/output/compromise_decisions.tsv`

Header, exactly:

```text
signer_id	state	effective_on	reason
```

Write one row for every signer in `/app/recovery/candidate-snapshot.tsv`, sorted alphabetically by `signer_id`. `state` is exactly `clear` or `blocked`. Use the latest matching compromise-ledger record for the requested incident whose `effective_on` is on or before the recovery date. A later clearance overrides an earlier block. When no matching record applies, write `clear` and leave both `effective_on` and `reason` empty.

### `/app/output/signer_quorum.tsv`

Header, exactly:

```text
role	signer_id	priority	region	key_family	assurance_weight	public_key_sha256
```

Write one row per selected signer, sorted first by `role` in ascending alphabetical order and then by `signer_id` in ascending alphabetical order. `priority` and `assurance_weight` are integers. `public_key_sha256` is the lowercase SHA-256 of that signer's verification material.

### `/app/output/delegation_paths.tsv`

Header, exactly:

```text
role	signer_id	root_id	hops	delegation_path	custodian	risk_score
```

Write one row per selected signer in the same role-then-signer order as `signer_quorum.tsv`. `hops` and `risk_score` are integers. `delegation_path` lists every node from root to signer joined by the single character `>` with no spaces, for example `root-a>bridge-a>signer-a`.

### `/app/output/delegation_witnesses.tsv`

Header, exactly:

```text
signer_id	root_id	edge_count	status
```

Write one row for every input path, preserving the row order from `delegation_paths.tsv`. `edge_count` is an integer and must equal the number of edges in the path. `status` is exactly `valid` or `invalid`. The Lua verifier must write the witness row even for an invalid path and must exit non-zero if any row is `invalid`.

All JSON files below must be compact JSON objects. Keys must appear in the exact order shown. SHA-256 values are lowercase hexadecimal strings. Arrays of signer IDs, regions, and roots are sorted alphabetically. Integer totals are JSON numbers, not strings.

## `/app/trust/release-policy.json`

Update this existing file in place. Its 17 keys, in order, are:

1. `allowed_model_kind` — string; `logistic_regression`
2. `assurance_weight` — integer; sum for the selected panel
3. `candidate_snapshot_sha256` — SHA-256 of `/app/recovery/candidate-snapshot.tsv`
4. `compromise_decisions_sha256` — SHA-256 of `/app/output/compromise_decisions.tsv`
5. `compromise_ledger_sha256` — SHA-256 of `/app/recovery/compromise-ledger.jsonl`
6. `delegation_state_sha256` — SHA-256 of `/app/recovery/delegation-state.tsv`
7. `delegation_witnesses_sha256` — SHA-256 of `/app/output/delegation_witnesses.tsv`
8. `incident_id` — string from the recovery request
9. `maximum_threshold` — number from `/app/config/screening.json`
10. `minimum_threshold` — number from `/app/config/screening.json`
11. `model_sha256` — SHA-256 of `/app/model/metadata.json`
12. `previous_policy_sha256` — digest from the immediately preceding release-history row
13. `regions` — sorted array of distinct selected regions
14. `release_sequence` — rollback-safe integer sequence
15. `signer_id` — alphabetically first selected signer; this is the primary signer
16. `signer_ids` — sorted array of all selected signers
17. `trust_roots` — sorted array of distinct selected delegation roots

## `/app/output/quorum_summary.json`

Its 7 keys, in order, are:

1. `assurance_weight` — integer panel total
2. `delegation_roots` — sorted array of distinct roots
3. `regions` — sorted array of distinct regions
4. `signer_count` — integer number of selected signers
5. `signer_ids` — sorted array of selected signers
6. `total_priority` — integer panel total
7. `total_risk` — integer custody-risk total

## `/app/output/recovery_audit.json`

Its 11 keys, in order, are:

1. `candidate_snapshot_sha256`
2. `compromise_decisions_sha256`
3. `compromise_ledger_sha256`
4. `delegation_state_sha256`
5. `delegation_witnesses_sha256`
6. `incident_id`
7. `policy_sha256` — SHA-256 of the published policy bytes
8. `previous_policy_sha256`
9. `release_sequence` — integer
10. `signature_count` — integer number of selected signers
11. `signer_ids` — sorted array of selected signers

The digest and incident fields use the same sources as the release policy.
