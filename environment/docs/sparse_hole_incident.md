# Sparse-hole mirror incident notes

Operations minimized this report from a replica site where an inplace block transfer survived a mid-transfer network drop. Destination length and mtime matched the source catalog, yet an independent content probe still showed elevated generation while sparse hole clusters remained uncleared. Uptime checks stayed green because they consult catalog state flags rather than hole-debt and content-catchup ledgers.

This workspace simulates that incident with the bundled blkmir maintenance controller. Correctness depends on dual-axis settlement: hole-ledger clearance and content-generation catchup must both complete before verified bytes catch synced presentation bytes and destination-leg hold/epoch may advance.

See `operator_notes.md` for replay commands, fixture layout, and export schemas.
