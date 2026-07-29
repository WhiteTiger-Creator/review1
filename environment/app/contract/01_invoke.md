# 01 — Invocation and outputs

```
make -C /app dispatch PANEL=<panel-dir> OUT=<out-dir>
```

Default handoff: `PANEL=/app/panel` and `OUT=/app/out`.

- Resolve `OUT` to a real path. Publishing is allowed only when the resolved
  directory is `/app/out` or a subdirectory of `/app/out`. Any other `OUT`
  (for example under `/app/notes`) must be rejected: write no product files
  there and exit non-zero.
- **OUT hygiene (every run, sound or unsafe):** the resolved OUT directory may
  contain only `.keep`, plus `beacon.queue` and `runner.fold` on sound boards.
  At the **start** of every run, remove every depth-1 entry under OUT except
  `.keep` (files and subdirectories). Do **not** delete `.keep`. At the **end**
  of every run, ensure the same rule still holds (unsafe: only `.keep`; sound:
  `.keep` plus the two products). Scratch, temp dirs, and diagnostics must never
  remain under OUT — use `/app/notes` for scratch.
- After every finished run (sound **or** unsafe), `/app/out` must still contain
  a `.keep` file. Creating `.keep` if missing is allowed; deleting it is never
  allowed.
- Scratch may be written under `/app/notes` during a run. When finished (sound
  or unsafe), leave `/app/notes` containing only `.keep`.
- Sound boards publish exactly `beacon.queue` and `runner.fold` (LF endings,
  final newline) and exit status `0`.
- Unsafe boards leave the output directory empty except `.keep` and MUST exit
  non-zero. Every unsafe condition requires both effects: products removed and
  non-zero exit from `make dispatch`.

Optional panel file `FORCE_FAIL`: if present as a regular file, exit non-zero
after clearing products (and after OUT hygiene above).

Comment lines starting with `#` are ignored in every table. Blank lines are
ignored. TSV files use a header row; column order is fixed by header names.

Required panel files: `clock.txt`, `lamps.tsv`, `flaps.tsv`,
`acknowledgements.tsv`, `blackouts.tsv`, `corridors.tsv`, `bells.tsv`,
`promotions.tsv`, `operators.tsv`, `widths.tsv`.
