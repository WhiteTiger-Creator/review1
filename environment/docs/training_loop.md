# Training sampler notes

Local curriculum-learning trainer for model-example difficulty banding across training epochs. Packs under `/app/packs` are training scenarios. Policy knobs for the training loop live in `/app/docs/pol_a.toml`. Public training invariants and the cohort trace schema live in `/app/docs/cur_contract.md`.

The training harness builds `/app/bin/cqrun` and emits training/evaluation admissions into `/app/output/cohort_trace.json` with durable checkpoint state under `/app/output/cohort_state`.
