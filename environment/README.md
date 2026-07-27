Coastal plastics quality-model fit-score desk.

Pinned model card and weights live under `models/`. Feature tensors for the
primary train split and held-out eval split live under `fixtures/primary` and
`fixtures/hold`. The evaluate entrypoint fit-scores via `drive_k4.sh` (fit
checkpoint, then inference + evaluation loss + deployment gate). Recover is
`recover_k4.sh`. Public metric rules are under `docs/`. Evaluation journal
records may already exist under `var/journal/`. Generated evaluation artifacts
land under `/app/output/`. Durable seal state lives under
`/app/var/psr/eval_seal.json`. Fit writes `/app/var/psr/quality_checkpoint.json`.
