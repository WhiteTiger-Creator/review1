Complete the Anisotropic deterministic arena replay analyzer in `/app/environment/src/flux_recon.cpp`.

The program reads every `*.flux` replay case from `/app/environment/cases` unless `--case-dir <path>` is supplied. It writes `/app/output/flux_report.json` unless `--out <path>` is supplied. It must implement the complete visible contract in `/app/environment/docs/reconstruction_contract.md`.

This is a strategy-game replay task, not a numerical-fitting task. Each case describes a grid arena, actors, portals, and per-round commands. Your analyzer must simulate all rounds exactly, including dash microsteps, portal teleports, one-round echo trails, simultaneous move conflicts, direct swaps, iterative occupancy blocking, energy updates, pressure gates, charge tiles, turret line-of-sight attacks, exits, event ordering, scoring, and canonical FNV-1a digests.

The internal `case_id` inside a `.flux` file is authoritative. File names are only containers and may differ from `case_id`; do not use file names for sorting, validation, output fields, or digest tokens.

Important parsing details: trim leading and trailing whitespace from every input line before comment checks, tokenization, or grid-row length checks. This means indented grid rows are valid after trimming. Bump events must include the winner id exactly as `r<round>:<actor>:bump:<winner>`; do not emit a shorter `:bump` event.

The verifier uses bundled fixtures and freshly generated replay cases with different paths and edge cases. Implement the generalized replay rules rather than memorizing bundled case outputs. Invalid `.flux` inputs must exit with code `2`, delete any stale output file, and print a diagnostic to stderr containing `invalid` or `error` after lowercasing.

The JSON schema is exact. Do not add unlisted keys, debug counters, timestamps, raw input paths, or comments. The digest is computed from canonical tokens described in the contract, not from pretty-printed JSON.
