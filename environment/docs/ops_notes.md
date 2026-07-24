# Operator notes

Offline span screening sweeps use bundled cases under `cases/`.
The bash entry is `exec/kit.sh`. It builds Rust `w2` and Go `xq7`, then regenerates `/app/output/span_parity.json`.

## Case inventory

- `c_a.json` (single midspan load)
- `c_b.json` (two symmetric loads)
- `c_c.json` (off-midspan single load)
- `c_d.json` (stiffer section, short span)
- `c_e.json` (long span, soft section)
- `c_f.json` (three uneven loads)
- `c_g.json` (matched EI load ladder companion for linearity)
- `c_h.json` (wide geometry extremes, coarse/fine mesh split)
- `c_i.json` (five-load dense asymmetric span)
- `c_j.json` (near-support heavy/light load pair)
- `c_k.json` (coarse/fine mesh contrast with triple mid-band loads)
- `c_l.json` (stepped four-load force ladder)
- `c_m.json` (six-load irregular long-span cluster)

## Case JSON shape

Each case JSON object includes `case_id` (string), `length_m` (span length, number), `e_pa` (modulus, number), `i_m4` (second moment, number), `n_coarse` (coarse element count, number), `n_fine` (fine element count, number), and `loads` (array).

Each load object includes `id` (string), `x_m` (position along the span, number), and `force_n` (point force, number).

## Environment variables

- `APP_ENV_ROOT` — environment root (default `/app/environment`)
- `BEAM_OUT` — report path (default `/app/output/span_parity.json`)
- `BEAM_RUN_ID` — run identifier for scratch slot helpers

Do not rely on network fetches. Keep runs local and deterministic.
