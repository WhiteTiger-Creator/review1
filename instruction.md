Train and evaluate a plastics feature-quality model under `/app/environment`.

Pinned model card and weights live under `/app/environment/models/checkpoint.json` and `/app/environment/models/weights.json`. Feature tensors for the primary train split and held-out eval split live under `/app/environment/fixtures/primary` and `/app/environment/fixtures/hold`. Channel slopes and quality-class cuts stay on those packs. Evaluation loss, calibration ladder, deployment-gate rules, tolerances, schema, and eval-seal lineage live under `/app/environment/docs/pol_n.rst`, `tol_n.rst`, `sch_n.txt`, and `seal_n.rst`.

Run `bash /app/environment/drive_k4.sh` so the desk fit-scores: fit a quality checkpoint from the primary train split into `/app/var/psr/quality_checkpoint.json`, then run inference on primary and held-out packs. Produce `/app/output/obs_primary.json`, `/app/output/obs_hold.json`, `/app/output/rights_map.json`, and `/app/output/transparency.txt`, overwrite them every run, rewrite `/app/run/psr_ledger.jsonl`, and leave a COMMIT eval seal at `/app/var/psr/eval_seal.json` whose `gen` and `eval_fp` match the observation roots and rights sheet. Static outputs are not enough; training-checkpoint fit, inference, evaluation loss, deployment gating, and seal lineage under `/app/environment` must regenerate matching artifacts.

Held-out evaluation must satisfy the published metric on both splits:

- Inference: quality scores, class ladders, and band digests match `pol_n`, including after journal-seeded resume and after class transitions that discard stale resolution-cache entries.
- Evaluation loss: Q recomputes from current bands and ladder on every call, including campaign replay (`mode >= 1`); a journal prior must not be returned as Q.
- Deployment gate: grants follow ladder maxima; `neg` and transparency list exactly the `ng:{k}` tokens for degraded classes across both roots.

The same obligations apply after fixture pack values change; digests and journals must track live packs, including each pack `gen`. `/app/environment/recover_k4.sh` rebuilds the four artifacts from the ledger under a COMMIT seal whose `eval_fp` matches the live fixture tree. Missing, OPEN, or fingerprint-mismatched seals exit non-zero. Recover does not re-run inference on fixture packs.

Each evaluate fit must rewrite `/app/var/psr/quality_checkpoint.json` from the live primary train split so `checkpoint_digest` tracks primary fixture bytes. Journal seeds may exist under `/app/environment/var/journal`. Rights sheet `version` stays `k4-1`. Optional argv: `bash /app/environment/drive_k4.sh --help` and `bash /app/environment/drive_k4.sh --root /app/environment --out /app/output`. Unknown flags exit 2.
