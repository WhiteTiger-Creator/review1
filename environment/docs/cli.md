# Chironym CLI

Binary: `/app/bin/chironymctl` (built from `/app/environment`).

## prepare

```bash
/app/bin/chironymctl prepare --output /app/output
```

Creates the output directory, writes `/app/output/chironym_prepared.json` with `{"armed": true, "generation": N}` where `N` increments each successful prepare on that directory (starting at 1). Creates `/app/var` if needed.

## evaluate

```bash
/app/bin/chironymctl evaluate --campaign <campaign_dir> --output <output_dir>
```

Requires `<output_dir>/chironym_prepared.json` with `armed: true`. Otherwise fails with stderr beginning `chironym output not armed:`.

On success writes the artifacts listed in `contracts.md` and prints the required stdout lines.

Helper binaries used during evaluate (must remain on PATH / under `/app/bin`):

- `/app/bin/k7` — line protocol (`DIM`/`TAU`/`LR`/`STEPS`/`TOKEN`/`PAIR a|p`/`END`) → `E <token> v0,...,vD` lines
- `/app/bin/m3` — line protocol (`GAMMA`/`GAP`/`HYP a|b`/`REF a|b`/`E token vals`/`END`) → `RAW` and `SCORE` lines
