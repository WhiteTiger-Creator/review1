# Required edge classes

Package arms use keys `a7` and `b2`.

## Arm a7

Required classes on the effective probe:

- `root`
- `bind`
- `prop`

## Arm b2 / dual

Required classes on the effective dual-arm probe:

- `root`
- `bind`
- `sys`
- `prop`

`--arms a7` alone must omit `sys` and must omit b2-only modules entirely from both the `require` and `replace` blocks in nest/go.mod (regenerate go.mod strictly from the arm's plan edges). Dual `a7,b2` keeps shared surfaces plus both arm-only modules.
