# Design notes

Anisotropic arena cases are deterministic strategy-game replay puzzles. The visible contract in `reconstruction_contract.md` is authoritative for simulation, scoring, output, and digest rules.

The Anisotropic arena includes stateful pressure gates, charge tiles, and turret line-of-sight effects so replay correctness depends on multi-round arena state, not only local moves.

Input files may be indented in generated tests; the replay contract intentionally trims each line before token and grid processing.
