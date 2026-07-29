# Settlement overview

This workspace models inplace block mirroring after a network drop. Catalog presentation can report `finished=true` while sparse unwritten clusters (`hole_debt`) and content-generation catchup remain incomplete. The independent probe view tracks hole and content axes separately from catalog presentation generation.

Stage marks in probe fixtures:

- `present_mark` — presentation/sync bytes staged
- `hole_clear_mark` — hole-ledger debt clearance applied
- `content_mark` — content-generation catchup applied

Progress ops map to those stages as `chunk`, `roll`, then `latch` (present, hole-clear, content). Byte settlement treats synced presentation bytes and verified settlement as distinct: verified may match synced only after hole debt is cleared and content catchup completes. Destination-leg hold timing follows `config/push.toml` `hold_us` once both settlement axes and destination IO are complete.

Lane routing for digest epochs is in `config/epoch_lane.toml` (`catalog_lane` and `probe_lane`). Packing must load that table at runtime rather than assuming equal lanes. Finished catalog presentation must not re-route catalog-side digest epoch to the probe epoch while hole debt or content catchup remains open. Leg-b segment advancement requires destination IO plus both settlement axes; partial axis closure alone must not raise hold timing or leg-b epoch. Append resume rebuilds segment floors from the active fixture pair and lane config rather than from partial prior convergence rows. See `export_contract.md` for export field contracts and `operator_notes.md` for replay commands.
