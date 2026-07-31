# Architecture

`tak-road` loads sealed season floors, reads static board fixtures, detects
roads and flat counts, applies victory gates, and writes the championship
scoreboard.

Packages:

- `season` — profile load, seal verify, overlay handling
- `board` — scenario fixtures and stack tops
- `pathing` — road connectivity
- `flats` — flat-count tallies
- `victory` — ordered gates
- `bracket` — points, standings, summary, report write

Binary: `/app/bin/tak-road`.
