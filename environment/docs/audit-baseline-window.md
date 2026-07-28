# Audit Baseline Window

Specification for `audit-baseline-window`, a read-only report over the
current `audit_log` table. Like `tier` in `regional-classification.md`,
this is not a stored column: it is recomputed fresh from the full
`audit_log` table, in `seq` ascending order, on every call.

## A Bounded Reference Set

At most 2 rows across the whole `audit_log` table -- not per-country, not
per-region, not per-income-level -- may count as part of the trusted
reference set (`baseline`) at the same time. Every other row is
`provisional` until it is admitted. Once a row is admitted into the
baseline it stays there; nothing ever moves a row back to provisional.

## Reference Rows Age Out On A Delay

A row holds its baseline slot for 3 more rows after the row itself joined
the baseline, then ages out and frees the slot for another row -- the
age-out point is 3 rows after the step at which that row was actually
admitted, not 3 rows after its original seq. A row admitted immediately on
arrival ages out 3 rows after its own seq. A row that sat provisional for a
while before finally being admitted ages out 3 rows after the row at which
it was admitted, not 3 rows after its original seq.

## Provisional Rows Are Admitted Strictly In Log Order

When a slot frees up, it goes to whichever currently-provisional row has
been waiting longest -- never to a row just because that row happens to be
the one logged in the same step that freed the slot. A row newly added at
the current step joins the back of any existing backlog of provisional
rows; it is not admitted ahead of rows that were already waiting, even
when the slot that opens at that same step has nothing to do with this new
row.

## Output

`audit-baseline-window` prints one line per `audit_log` row, in `seq`
ascending order:
```
<seq>\t<country_code>\tstatus=<baseline|provisional>
```
After all rows, a final line reports how many reference slots remain open
once every row currently in the table has been processed:
```
window_remaining=<N>
```
If `audit_log` is empty, prints `empty` and exits 0.
