# RTS skirmish map weathering

This workspace holds a deterministic Java skirmish-map weathering pass for
battlefield tiles. The build entrypoint is under `scripts/`; game sources are
under the package tree; profiles, map data, and public contracts live beside
them.

Public contracts are in `docs/skirmish_contract.md`. The normal entrypoint is
`scripts/build_and_run.sh`, which regenerates `/app/output/field_report.json`.
