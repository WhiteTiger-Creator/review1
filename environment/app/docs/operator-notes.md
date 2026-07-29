# Operator notes

Use `/app/scripts/build-gateway.sh`, `/app/scripts/run-admission.sh`, and
`/app/scripts/check-admission.sh` to build, evaluate, and validate the supplied release request.
Temporary evaluation state must remain outside the committed `/output` generation.

The workspace under `/app` is a multi-crate admission gateway: signed envelopes, trust and
delegation state, artifact-graph closure, policy evaluation, evidence construction, legacy
compatibility, and atomic publication. Library behavior used during evaluation must be
correct, not only the CLI wrapper.

The operator-facing CLI is `/app/bin/admission-gateway` (backed by the release binary under
`/app/target/release/`) with these subcommands:

- `evaluate --request <path> --output <dir>` — admit or reject and publish outputs
- `inspect --request <path>` — print a request/closure summary
- `inspect --evidence <path>` — print an evidence summary
- `verify --request <path> --decision <path> --evidence <path>` — bind-check a generation

The offline verifier rebuilds the gateway from source and re-runs admission against the
rebuilt binary. The binary must remain an ELF artifact. Pytest may emit CTRF via `--ctrf`.

Offline Cargo builds set `CARGO_NET_OFFLINE=true` and use the vendored crate
tree produced during image build. Do not restore network access for workspace
builds.

Migration and delegation records expose solver-visible fields such as
`from_principal`, `to_principal`, `subject_principal`, `namespace_pattern`,
`predicates`, `public_key`, and `valid_from_epoch`.
