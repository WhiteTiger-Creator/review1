# Audit Log Chain Specification

## Purpose
The audit log provides a tamper-evident record of every country fetch operation.
Any modification to historical data will break the chain and be detected by `audit-verify`.

## Chain Bootstrap
The first entry (seq=1) uses a `prev_hash` of 64 zero characters:
`0000000000000000000000000000000000000000000000000000000000000000`

## Sequential Linking
Entry N's `prev_hash` = Entry (N-1)'s `entry_hash`.
This links every entry to its predecessor, making the chain tamper-evident.

## HMAC Computation
For entry with seq=S, country_code=C, latitude=LAT, longitude=LON,
skewness_at_insert=SKEW, kurtosis_at_insert=KURT, p50_at_insert=P50,
mad_at_insert=MAD, prev_hash=P:
```
message = fmt.Sprintf("%d|%s|%.6f|%.6f|%s|%s|%.6f|%s|%s", S, C, LAT, LON, SKEW, KURT, P50, MAD, P)
entry_hash = hex(hmac_sha256(key="wb-tracker-secret-2026", message))
```
See `hmac-spec.md` for the full field-by-field breakdown (NULL rules for
`SKEW`/`KURT`/`MAD`, formatting and algorithm for `P50`/`MAD`, etc.) — this is the same message format
used for the standard forward chain, `country-chain-dual`'s forward chain, and
`audit-verify`.

## Atomicity
The country INSERT and audit_log INSERT should be performed in the same transaction
to prevent partial writes that would corrupt the chain.

## country-chain-dual

Computes both a forward and reverse HMAC chain over the `audit_log` table and
prints both terminal hashes.

Forward chain: computes `entry_hash` for each row in seq order (1, 2, ..., N).
The forward hash output is the `entry_hash` of the row with the maximum seq
(same computation as the standard chain above).

Reverse chain: iterates the `audit_log` rows in DESCENDING seq order (N,
N-1, ..., 1). Maintains a running `prev_rev_hash` starting as 64 zero
characters. For each row (in descending seq order):
```
rev_hash = HMAC-SHA256(key="wb-tracker-reverse-2026",
  message="<seq>|<country_code>|<lat:.6f>|<lon:.6f>|<prev_rev_hash>")
```
where lat and lon are formatted to exactly 6 decimal places. After all rows,
`prev_rev_hash` is the final reverse hash. Note the reverse chain uses a
different HMAC key (`wb-tracker-reverse-2026`) and a shorter message format
than the forward chain (no skewness/kurtosis/p50/mad fields).

Output format:
```
fwd=<forward_hash>
rev=<reverse_hash>
```
If `audit_log` is empty, prints:
```
fwd=0000000000000000000000000000000000000000000000000000000000000000
rev=0000000000000000000000000000000000000000000000000000000000000000
```
Exits 0 always.
