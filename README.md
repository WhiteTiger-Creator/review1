# Notes for reviewers

## Layout

- `environment/dpx` — the DPX/1 package tool the box ships. Inspection subcommands plus the
  `install --force` repair hatch. It has no recovery subcommand and no config-aware upgrade
  path; transactions are driven by an orchestrator that does not run on the boxes.
- `environment/docs/dpx-1.md` — the on-disk contract. Formats, ownership, the config-file
  promise, directory handling, the transaction stages, the journal record table and its
  write ordering, and what closing an interrupted transaction means.
- `environment/root/` — the machine as it came back up, copied to `/` at build time. Package
  database, two journals, cached archives, and the file tree the interrupted run left behind.
  File modes carry over from the build context, so the staged leftovers arrive at 0600.
- `tests/fixtures/` — the expected state of this box after recovery, plus four held-out roots
  the verifier materialises itself and runs the delivered reconciler against. Content is
  stored as plain text; the cached archives are hex.

## Verifier

`tests/test_outputs.py` is in two halves. The preservation half reads files only, so it
passes on an untouched box and has to keep passing; the reconciliation half covers this
box's root and the four held-out roots. Nothing in the suite calls the on-box `dpx` binary —
the agent can edit that — so the consistency rules are re-implemented in the test file.

## Reproducing the environment

The seeded box and the fixtures are generated, not hand-written. The generator is a forward
DPX/1 simulator kept outside this directory; the expected post-recovery state is computed by
running the same transaction forward to completion, which is an independent path from the
oracle's recovery logic and cross-checks it.
