# State schemas

See `rollout_contract.md` for behavioral rules. File shapes:

## registry.json

Checkpoints with `id`, `parent`, `feature_epoch`, `tokenizer_id`, `adapter_id`, `sha`, plus `active` hint.

Fixture checkpoint ids: `ckpt_root` means the seeded complete tip; `ckpt_mid` means the child of root; `ckpt_tip` means the child of mid; `ckpt_badtok` and `ckpt_badadp` mean incompatible siblings that must fail promote. Parent links and tokenizer/adapter fields live in `/app/environment/irc/fixtures/registry.json`.

## journal.ndjson

`journal.ndjson` means the promotion journal: one JSON object per line with `seq`, `op` (`promote`|`rollback`), `ckpt`, `generation`, `complete`, `feature_epoch`.

## router.json

`generation`, `checkpoint_id`, `routes` (shard targets).

## feature_bind.json

`feature_epoch`, `bound_generation`, `valid`.

## materialized.json

`epoch`, `generation`, `fresh`.

## serving_profile.json

`tokenizer_id`, `adapter_id`.

## eval_policy.json

`min_feature_epoch`, `require_fresh_materialization`.

## status.json

`active_checkpoint` means the journal-authoritative serving checkpoint id. `materialization_fresh` means whether `materialized.json` reports `fresh` true. Also includes `generation`, `journal_tip_seq`, `feature_valid`, `feature_epoch`.

## eval_binding.json

`eval_binding.json` means the graded evaluation view written by `eval-bind`. Fields: `generation`, `checkpoint_id`, `feature_epoch`, `router_digest`, `journal_tip_seq`, `compatible`, `lineage_proof`.
