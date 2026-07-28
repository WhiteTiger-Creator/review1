# Offline PMT waveform calibration workspace

Operator note. This tree reduces PMW2 waveform acquisition shards from the calorimeter
photomultiplier test stand into a per-lane gain table:

```bash
python3 /app/environment/hvreduce.py calibrate <profile>
```

Profiles are declared in `runbook/campaign.toml`. Acquisition shards live in `fixtures/` and
are read-only recorded data. A successful run writes
`/app/output/hv_gain_table.json` and `/app/state/hv_replay_ledger.json`; a run that
violates a documented contract writes nothing, prints the reason to standard error, and
exits `1`.

Every scientific and format contract this workspace is held to is written down under
`docs/`. Start with `docs/overview.md`, which indexes the rest: the PMW2
container layout and merge rules, baseline estimation and charge integration, the
rolling pedestal model, the generalized least squares fit, reference-lane normalization,
the published schema with its digests, and the bundled calibration profiles.
