Toolchain notes for the local kit.

Build requires Go 1.24+ on PATH. The shell entrypoint is `drive_k4.sh`.
Public rules live under `docs/`. Campaign corpora live under `corp/primary` and
`corp/hold`. Campaign journal records may already exist under `var/journal/`.
Generated artifacts land under `/app/output/` when the entrypoint runs with
default paths.
