# Inference rollout controller

Offline ML inference deployment under `/app/environment/irc`. Repair the controller so promote, rollback, recover, and eval-bind keep registry, journal, derived router, feature bindings, and feature materialization consistent under the evaluation policy.

## Paths

- Controller: `/app/environment/irc/`
- State: `/app/environment/irc/state/`
- Fixtures: `/app/environment/irc/fixtures/`
- Outputs: `/app/output/status.json`, `/app/output/eval_binding.json`
- CLI: `/app/environment/irc/cmd/irc`

## Commands

```
irc status
irc promote --ckpt <checkpoint_id>
irc rollback --generation <n>
irc recover
irc eval-bind
```

`status` and `eval-bind` write under `/app/output/`. Mutating commands change only `/app/environment/irc/state/`.

## Authority

The last **complete** journal event is authoritative for active checkpoint and generation. `registry.json` `active` is a cache hint. After `recover` or any mutating reconcile, journal wins when they disagree.

Incomplete events (`complete: false`) never become active. `recover` truncates incomplete trailing journal lines and removes `state/staging/` before rebinding derived state.

Operator notes under `/app/environment/irc/notes/` are non-authoritative.

## Lineage gate

A checkpoint with non-null `parent` may be promoted only if that parent already appears as `ckpt` on some complete journal event. Promoting a descendant without an ancestor tip fails with exit code 2 and must not mutate journal tip, router, feature binding, or materialization.

## Generations and feature binding

Each successful non-idempotent promote assigns `generation = last_complete.generation + 1` (or 1 if none). After the fixture root tip at generation 1, the first successful promote of `ckpt_mid` therefore lands at generation 2. Rollback appends a complete event targeting an earlier complete **promote** generation and restores that generation's checkpoint.

`feature_bind.json` must set `feature_epoch` to the active checkpoint's required epoch, `bound_generation` to the active generation, and `valid: true` after successful promote/rollback/recover rebind.

## Materialization

`materialized.json` records the feature store view: `{ "epoch", "generation", "fresh" }`. After a successful promote or rollback, rewrite it so `epoch` and `generation` match the active tip and `fresh` is true. If recover finds materialization out of sync with the complete tip, set `fresh` to false until a successful promote or rollback rebinds it.

## Compatibility

Promote fails (exit 2) when checkpoint `tokenizer_id` or `adapter_id` disagrees with `serving_profile.json`. Failed promotes must not append a complete journal event and must not change router, feature_bind, or materialization.

## Idempotency

`promote --ckpt X` when X is already the complete tip's checkpoint exits 0 without appending a journal event and without bumping generation. Derived files may be rewritten to the same logical values.

## Atomicity

Promote writes `state/staging/intent.json` then commits. Staging with intent and no matching complete journal event means the promote did not finish; `recover` clears it.

## Evaluation policy

`eval_policy.json` holds `{ "min_feature_epoch", "require_fresh_materialization" }`. Graded evaluation may substitute stricter held-out policies (for example verifier packs named like `eval_policy_threat.json`) before scenarios. `eval-bind` sets `compatible` true only when:

- feature binding is valid,
- materialization is fresh when required,
- active `feature_epoch` is at least `min_feature_epoch`.

## Status output

`status` writes `/app/output/status.json` with `active_checkpoint`, `generation`, `journal_tip_seq`, `feature_valid`, `feature_epoch`, and `materialization_fresh`.

## Eval binding

`eval-bind` rebuilds the router from the complete tip, then writes `/app/output/eval_binding.json`:

- `generation`, `checkpoint_id`, `feature_epoch`, `journal_tip_seq`
- `router_digest`: first 16 hex chars of sha256 over canonical JSON `{"generation","checkpoint_id","routes"}` (insertion order)
- `compatible`: boolean per evaluation policy
- `lineage_proof`: first 16 hex chars of sha256 over the UTF-8 string  
  `{seq}|{checkpoint_id}|{generation}|{feature_epoch}|{router_digest}|{materialized.epoch}|{materialized.fresh}`  
  where `fresh` is serialized as `true` or `false`

Hand-written outputs are insufficient: the verifier clears `/app/output` and re-runs CLI sequences.
