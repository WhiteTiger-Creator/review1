# Output file format

The program writes one plain-text report per case to the output path given as
the second argument.

    n=<n>
    status=OK
    message=<text>
    X
    <row 0: n numbers>
    ...
    <row n-1: n numbers>
    Z
    <row 0: n numbers>
    ...
    <row n-1: n numbers>
    SCALE
    <mu_0>
    <mu_1>
    ...
    <mu_23>

Field meaning:

- `n` — the order of the matrix, echoed back.
- `status` — `OK` when a result was produced.
- `message` — free text, `none` when there is nothing to report.
- `X` — the first result matrix, `n` rows, `n` entries per row.
- `Z` — the second result matrix, `n` rows, `n` entries per row.
- `SCALE` — the scale trace of the pinned iteration in `problem_statement.md`,
  exactly `K = 24` values, one per line, `mu_k` on line `k` (0 based).

Numbers are written in decimal with full double precision.
