# CLI contract — `/app/bin/pabcal`

```
/app/bin/pabcal [--lattice PATH] [--desk PATH] [--weights PATH] [--report PATH]
```

Order free. Pair each flag with a value.

Defaults:

- lattice: `/app/data/sample_array.csv`
- desk: `/app/config/cal_policy.toml`
- weights: `/app/weights_table.csv`
- report: `/app/desk_summary.json`

| exit | meaning |
| --- | --- |
| `0` | valid, no outliers; write both artifacts; empty stdout |
| `1` | valid, ≥1 outlier; still write both; empty stdout |
| `2` | fatal CLI/input/policy/validation; non-empty stderr; do not create or clobber `--weights` / `--report` |

Fatal CLI: unknown flag, duplicate flag, missing value, path collision among the four roles.

Fatal input/policy (also exit `2`, same no-clobber rule): live/sealed policy keys invalid or `schema_version != 8`, CSV header names/order wrong, duplicate/empty antenna ids, frequency spread beyond policy, missing or duplicated `ref_antenna_id`, non-finite fields, empty array.

Atomic temp-then-rename writes. Create parent dirs on successful emit only.
