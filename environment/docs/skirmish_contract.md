# Skirmish map weathering contract

The production skirmish grid is 128 columns by 96 rows. A run has four steps.
The working-set ceiling is 4096 cell records. Reported floating values use
binary64 encoding, and the absolute comparison tolerance is 2.0e-12.

## field_report.json

Top-level fields include `grid_width`, `grid_height`, `steps`, `budget_cells`,
`peak_cells`, `tile_count`, `initial_sediment`, `final_sediment`,
`sediment_error`, `reduction_digest`, and `runs`. Each element of `runs` carries
`step`, `terrain_sum`, `water_sum`, `sediment_sum`, and `edge_export`. Profile
rain input uses `rainfall` / `rainfall_csv`.

The map is divided into 16 by 8 tiles (8 tile columns and 12 tile rows), for
96 complete tiles. When one tile is resident at a time, the peak working set
equals 128 cell records. The primary profile is selected with no argument; the
alternate rain profile is selected with `--alternate`. Each profile points at a
rain CSV through `rainfall_csv`; step rain follows that table in step order.

Terrain, water, and sediment totals are observations over all logical cells.
Edge export sums only border-cell transfers. The mud ledger balance is
`sediment_error = abs(final_sediment - initial_sediment)`.
The reduction order is row-major tiles, then row-major cells, with tile totals
added from left to right. Canonical run records use
`step|terrain|water|sediment|edge;` with twelve decimal places per floating
field. The digest is SHA-256 over the concatenated canonical text encoded as
UTF-8 and written as lowercase hexadecimal. The verifier recomputes that digest
with the same hashlib SHA-256 construction used for other local artifacts.
