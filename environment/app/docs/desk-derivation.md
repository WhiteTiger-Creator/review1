# Desk derivation (aperture calibration)

Shipped `/app/config/cal_policy.toml` is not authored by hand and must not be copied from a golden TOML (there is none in `/app/data`). Rebuild it from `/app/data/desk_journal.csv`. After a correct rebuild, the UTF-8 SHA-256 of the live file must equal the single hex digest in `/app/data/sealed/production_policy.sha256` (64 lowercase hex chars, optional trailing newline).

## Journal columns

Exact header:

```
field,vote,token
```

- `field` — policy key name (see `beamform-model.md`)
- `vote` — `yes` or `no`
- `token` — string payload (numeric tokens parse as floats/ints; string keys stay literal)

Blank lines and `#` comments are ignored. Strip a trailing CR before tokenizing. Exactly three comma-separated fields per data row.

## Selection

For every required policy key:

1. Collect rows with matching `field` and `vote == yes`.
2. There must be ≥1 such row.
3. Rows with `vote == no` are decoys and must not influence aggregates.
4. Unknown `field` names among `yes` rows are fatal for derivation.

Aggregates:

- **Float keys** — **midmean** of the parsed tokens: if fewer than 3 samples, ordinary median (even N → average of the two central values); otherwise drop one minimum and one maximum, then arithmetic-mean the rest. Do **not** use the plain arithmetic mean of all samples.
- **Integer keys** (`schema_version`, `wrap_half_open`, `phase_sign`, `geo_sign`, `ref_phase_align`) — arithmetic mean of the parsed integer tokens, then **ceil** toward `+∞` to an integer (e.g. mean `0.1` → `1`, mean `-1.2` → `-1`).
- **String keys** — among the `yes` tokens, take the **shortest** string; if several share that length, take the lexicographically least.

`schema_version` must evaluate to `8` after the integer rule above.

## Writing `/app/config/cal_policy.toml` (byte-exact)

Hard rules:

- UTF-8, LF only (`\n`), no CR
- No `#` comment lines
- No blank lines
- Exactly the required keys in the order listed in `beamform-model.md` (policy table order), one `key = value` per line
- No spaces before `key`; exactly one space on each side of `=`
- Integers without a decimal point
- Strings in double quotes
- Floats: if the value is a mathematical integer, print with a trailing `.0` (e.g. `25.0`); otherwise print with enough decimals then strip trailing zeros while keeping at least one digit after the decimal point (e.g. `0.15`, `0.018`)
- Single trailing newline after the last line

A leading comment, reordered keys, or `key=value` without spaces fails the SHA-256 check even when aggregates are numerically correct.
