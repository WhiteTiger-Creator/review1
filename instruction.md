The electromagnetic cavity solver under `/app/emsolve` produces inconsistent
physical mode payloads when the same cavity is described with different
vertex numbering, element ordering, local tetrahedron orientation, or
boundary-face listing, and checkpoint resume can disagree with a fresh run.
Repeated or clustered modes must expose deterministic canonical coefficient
payloads, including after checkpoint resume. Fix the C++ sources under
`/app/emsolve`, rebuild with `/app/scripts/build.sh`, and invoke the rebuilt
`/app/bin/emsolve` binary directly so `/output/modes.json` is produced by the
solver after a normal compile — not by hand-written output or wrapper
shortcuts.

`/app/docs/solver-contract.md` and `/app/docs/checkpoint-format.md` are
authoritative for the finite-element model, mode ordering, repeated-eigenspace
canonicalization, checkpoint binary layout, and resume validation. The public
CLI (`--mesh`, `--modes`, `--output`, `--config`, checkpoint flags, `--help`)
and `/output/modes.json` schema are unchanged. Do not modify shipped fixtures
under `/app/data`. Any mesh or checkpoint the contracts mark invalid must make
`/app/bin/emsolve` exit nonzero without a successful mode payload and must leave
an existing `--output` file untouched.
