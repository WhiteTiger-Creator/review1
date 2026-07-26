The command receives exactly one argument naming a UTF-8 JSON case file.
The root object contains `case_id`, `nodes`, `seed`, and `events`; unknown root fields may
be present and should be ignored (for example, `public`).

Evidence rows are processed in array order. The ledger clock starts at zero. Before
each row, if the row `time` is greater than the current clock, the clock is
advanced to that `time`. A `tick` then adds its `delta` to the clock.

Integer node identifiers range from zero through `nodes - 1`.
Malformed JSON should fail fast with a nonzero exit. Unknown row types inside
valid JSON are unfamiliar evidence rows and append a result with status
`"ignored"`, the current ledger clock, token from the row when present or zero
otherwise, and `write_id` from the row when present or the empty string
otherwise.

For lease and write rows, missing or empty `targets` means all nodes. Target
lists are normalized before quorum checks by ignoring out-of-range node ids and
deduplicating repeated node ids by their first occurrence.
