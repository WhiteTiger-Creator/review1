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

`--arms a7` alone must omit `sys` and must not keep b2-only nest requires. Dual `a7,b2` keeps shared surfaces plus both arm-only modules.
