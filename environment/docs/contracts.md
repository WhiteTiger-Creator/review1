# Chironym gloss alignment / selective-risk contracts

This document is the learning and reporting contract for the chironym evaluation desk.
All numeric formulas below are normative.

## Campaign inputs

A campaign directory contains:

- `pack.json` — `campaign_id` and `utterances[]` each with `utt_id`, `fold` (`train`|`calib`|`eval`), `hyp` (string tokens), `ref` (string tokens), `kin` (non-negative floats, length equals `len(hyp)`).
- `policy.json` — embedding and selective-risk knobs listed below.

Invalid campaign (missing files, empty utterances, fold not in the set above, `len(kin) != len(hyp)`, empty hyp/ref, non-finite kin, missing policy keys) must fail closed.

## Vocabulary and seed embeddings

Vocabulary = sorted unique tokens across all hyp and ref sequences in the pack.

For each token `g`, seed vector of dimension `D = policy.embed_dim`:

```
v0[g][k] = sin( ((fnv1a32(g) % 10007) + 1) * (k + 1) * 1e-3 )
```

Then L2-normalize each vector. `fnv1a32` is the standard 32-bit FNV-1a over UTF-8 bytes with offset basis `2166136261` and prime `16777619`.

## Contrastive embedding update (pairwise pull)

Positive pairs: for every utterance with `fold == "train"`, for `i` in `0 .. min(len(hyp), len(ref))-1`, the pair `(hyp[i], ref[i])` is a positive (including when the strings differ).

`tau = policy.infonce_tau` is reserved for future temperature scaling and must be read from policy but does not alter the update below.

Perform exactly `policy.infonce_steps` passes over all train positives in utterance order then pair-index order. For each positive `(a, p)` with learning rate `lr = policy.infonce_lr`:

```
mid = L2_normalize(emb[a] + emb[p])
emb[a] = L2_normalize( (1 - lr) * emb[a] + lr * mid )
emb[p] = L2_normalize( (1 - lr) * emb[p] + lr * mid )
```

Vectors are always L2-normalized after each assignment. After all steps, the embedding table is frozen for alignment.

## Soft-DTW alignment scores

For an utterance, build cost matrix:

```
C[i][j] = 1 - cosine(emb[hyp[i]], emb[ref[j]])
```

Let `gamma = policy.soft_dtw_gamma`, `gap = policy.gap_cost`.

Define softmin:

```
softmin_gamma(x, y, z) = -gamma * log( exp(-x/gamma) + exp(-y/gamma) + exp(-z/gamma) )
```

Prefix table `R` (0-based), sizes `n = len(hyp)`, `m = len(ref)`:

```
R[0][0] = C[0][0]
R[i][0] = C[i][0] + R[i-1][0] + gap    for i = 1..n-1
R[0][j] = C[0][j] + R[0][j-1] + gap    for j = 1..m-1
R[i][j] = C[i][j] + softmin_gamma(R[i-1][j], R[i][j-1], R[i-1][j-1])
```

Raw alignment cost `raw = R[n-1][m-1]`.
Quality score:

```
score = 1 / (1 + raw / max(n, m))
```

Token match rate `match_rate` = fraction of positions `i < min(n,m)` where `hyp[i] == ref[i]`, plus a length penalty: multiply by `min(n,m)/max(n,m)`.
Binary correctness label `y = 1` iff `match_rate >= 0.75`, else `0`.

## Temperature calibration

Use utterances with `fold == "calib"`.
For each temperature `T` in `policy.temp_grid`, compute mean binary NLL:

```
p = sigmoid(score / T)
nll = -( y*log(p+1e-12) + (1-y)*log(1-p+1e-12) )
```

Choose the `T` with minimum mean NLL (ties → smaller `T`).

Calibrated confidence for any utterance: `conf = sigmoid(score / T*)`.

## Selective risk gate

On `fold == "calib"` utterances only, evaluate each threshold `thr` in `policy.thr_grid`:

- Accepted set = calib utterances with `conf >= thr` (if empty, skip).
- Coverage = `|accepted| / |calib|`.
- Empirical risk = mean of `(1-y)` over accepted.
- Feasible iff empirical risk `<= policy.risk_target`.

Among feasible thresholds, choose the one with maximum coverage (ties → lower thr).
If none feasible, choose the highest thr in the grid (most selective) and still publish its coverage/risk.

On `fold == "eval"`, accept iff `conf >= thr*`.
Eval coverage/risk use the same definitions on eval utterances.

## Digests and state

`pack_digest` = lowercase hex SHA-256 of the canonical JSON of `pack.json` bytes as loaded (file bytes, not re-serialized).
`policy_digest` = lowercase hex SHA-256 of `policy.json` file bytes.
`embed_digest` = lowercase hex SHA-256 of a stable serialization: sorted tokens, each followed by comma-separated embedding floats formatted with 6 decimal places, newline-separated.
`bundle_digest` = lowercase hex SHA-256 of the concatenation `pack_digest + ":" + policy_digest + ":" + embed_digest + ":" + thr* formatted with 4 decimals + ":" + T* formatted with 4 decimals`.

`campaign_state.json` fields: `schema_rev` (always `1`), `campaign_id`, `epoch` (integer), `pack_digest`, `policy_digest`, `embed_digest`, `bundle_digest`, `temperature`, `threshold`, `eval_coverage`, `eval_risk`.

Epoch rules: start at `0` in empty state. Each successful evaluate increments epoch by 1. If `pack_digest` and `policy_digest` and `embed_digest` are unchanged from the previous successful state in `/app/var/chironym_state.json`, embeddings and scores must be byte-identical to the prior success outputs for the same campaign id; epoch still increments.

When policy `soft_dtw_gamma` or `gap_cost` or InfoNCE knobs change, embeddings and/or scores must recompute; digests must change accordingly. A stale in-process memo that ignores policy digest (or alignment/embed knobs) is incorrect.

## Output artifacts (success)

All under the armed output directory:

1. `align_report.json` — object with:
   - `schema_rev` (1)
   - `campaign_id`
   - `pack_digest`, `policy_digest`, `embed_digest`, `bundle_digest`
   - `temperature`, `threshold`
   - `calib_coverage`, `calib_risk`, `eval_coverage`, `eval_risk`
   - `utterances`: array of `{utt_id, fold, score, conf, accepted, y}` for every utterance sorted by `utt_id`
2. `utterance_scores.csv` — header `utt_id,fold,score,conf,accepted,y` then one row per utterance sorted by `utt_id`. Floats use 6 decimal places. `accepted` is `1` or `0`. `y` is `1` or `0`.
3. `eval_summary.log` — lines exactly:
   - `CAMPAIGN=<id>`
   - `TEMPERATURE=<T* with 4 decimals>`
   - `THRESHOLD=<thr* with 4 decimals>`
   - `EVAL_COVERAGE=<with 6 decimals>`
   - `EVAL_RISK=<with 6 decimals>`
   - `BUNDLE_DIGEST=<hex>`
   - `EPOCH=<int>`
4. `campaign_state.json` — as above.
5. `risk_history.jsonl` — append one JSON object per successful evaluate: `epoch`, `campaign_id`, `bundle_digest`, `temperature`, `threshold`, `eval_coverage`, `eval_risk`, `status` (`ok`).

CLI stdout on success must include lines:

- `TOP_ACCEPT_RATE=<eval_coverage with 6 decimals>`
- `BUNDLE_DIGEST=<hex>`
- `EPOCH=<int>`

Ledger `/app/var/chironym_ledger.json` is a JSON array. Each success appends `{campaign_id, bundle_digest, epoch, status:"ok"}`.

Persistent mirror state `/app/var/chironym_state.json` must match `campaign_state.json` after success.

## Negative paths

- Unarmed output directory: evaluate exits non-zero; stderr begins with `chironym output not armed:`; no success ledger row; no history append.
- Invalid campaign: exit non-zero; stderr begins with `invalid chironym campaign:`; no success ledger row; must not leave the five primary artifacts from a partial write for that evaluate (delete them if present at start of evaluate after arm check).

## Cross-artifact agreement

JSON, CSV, log, state, history row, ledger row, and CLI digest/epoch lines must agree on campaign id, digests, temperature, threshold, eval coverage/risk, and per-utterance score/conf/accepted/y for the same successful evaluate.
