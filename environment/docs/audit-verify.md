# Audit Verification

The `audit-verify` command iterates through all rows in `audit_log` ordered by `seq` and checks three conditions.

## Check Order (stops at first violation)
1. **seq_gap**: `seq` values must be consecutive starting at 1. If any gap is detected, report `TAMPERED seq=N reason=seq_gap`.
2. **prev_hash_mismatch**: for seq > 1, the stored `prev_hash` must equal the `entry_hash` of the previous row. Report `TAMPERED seq=N reason=prev_hash_mismatch`.
3. **entry_hash_mismatch**: recompute the HMAC for this row and compare to stored `entry_hash`. Report `TAMPERED seq=N reason=entry_hash_mismatch`.

## Success Output
`ok chain_length=N` where N is the total number of audit log entries verified.

## Exit Codes
- Exit 0: chain is intact
- Exit 1: any tamper violation detected

The audit log is append-only; no update or delete path should ever touch existing rows.
