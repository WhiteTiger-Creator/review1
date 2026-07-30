# RTS skirmish map weathering

The RTS skirmish map kiln under `/app/environment` weathers battlefield tiles
under a resident working-set budget and regenerates
`/app/output/field_report.json` from the bundled map inputs.
`/app/environment/scripts/build_and_run.sh` is the normal entrypoint; the
verifier rebuilds from source and deletes prior output, so a hand-written
report, stale artifact, wrapper-only change, or verifier edit is not
sufficient.

Budgets, tile streaming, rain profiles, report `runs` fields, mud-ledger
tolerance, and digest rules are in
`/app/environment/docs/skirmish_contract.md`. Keep the resident cell working
set inside the budget and report `peak_cells` from that resident set. Both the
default profile and the alternate profile selected through the build script
must work. Reruns of the same profile must be byte-identical.

Fix the game sources under `/app/environment` and let the normal commands
regenerate the report. Signal completion after the source and regenerated
report satisfy these requirements.
