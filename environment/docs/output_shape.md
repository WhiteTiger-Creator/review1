# Output shape

Primary artifact: `/app/output/perc_ledger.json` with schema `perc_model_v1`.

Top-level fields: `schema`, `journal_path` (`/app/var/model/active.page`),
`journal_generation`, `deny_count`, `updates`, `runs`.

Each run carries `action`, `case_id`, `outcome`, `reason`, `epoch`, `pred`,
`label`, `margin`, `digest`, `fence`, `persist_id`, `carried`, `lineage_skew`,
`notes`.

Durable pages: `/app/var/model/active.page`, `standby.page`, optional
`active.page.partial`.
