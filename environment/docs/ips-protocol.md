# Offline Bandit IPS / Doubly-Robust Evaluation Protocol (normative)

Offline policy evaluation for a contextual bandit CTR allocation head.
Logged interactions live under `/app/data/logs/interactions.jsonl`, the action
schema under `/app/features/action_schema.json`, the target evaluation policy
under `/app/models/target_policy.json`, and the reward model under
`/app/models/reward_model.json`.

## Purpose

The evaluation harness reads the inputs above, applies the temporal window,
propensity floor, importance weighting, and estimator rules below, and writes
`/app/output/ips_eval.json`.

## Stage A — Temporal eval window

Let `cutoff_unix` and `eval_window_sec` come from the primary config
(`/app/config/eval.json`).

- Eval events: `cutoff_unix <= timestamp < cutoff_unix + eval_window_sec`

Events outside this window must not contribute to weights, IPS, SNIPS, DR,
ESS, CI half-width, per-arm diagnostics, or serve gates.

For this release: `cutoff_unix = 1704067200`, `eval_window_sec = 604800`.

## Stage B — Propensity floor

After the temporal window, drop events with logging propensity
`propensity < propensity_floor`. Dropped events increment
`window.floor_excluded` and must not enter weight or estimator aggregates.
`propensity_floor` for this release is **0.01**.

Do not hard-code a different floor than the calibration stamp.

## Stage C — Join inventory

For every remaining in-window event, resolve:

- `π_e = target_policy.by_context[context_id][action]`
- `π_b = propensity` from the log row
- `q̂ = reward_model.by_context[context_id][action]`
- `direct = Σ_a π_e(a|x) * q̂(x,a)` over the action schema list

Drop events whose `context_id` or `action` is missing from the policy or
reward tables. `window.eval_rows` is the count of retained weighted events.

## Stage D — Importance weights (`weight_mode = "clipped_ratio"`)

```
w = π_e / π_b
if w > clip_max: w = clip_max
```

`clip_max` for this release is **10.0**.

Do not invert the ratio (`π_b / π_e`). Do not leave weights unclipped when the
ratio exceeds `clip_max`.

## Stage E — IPS estimator

Over the `N = eval_rows` retained events:

```
IPS = mean_i( w_i * r_i )
```

Round IPS to 6 decimal places.

## Stage F — SNIPS estimator (`estimator = "snips"`)

```
SNIPS = (Σ_i w_i * r_i) / (Σ_i w_i)
```

If `Σ w_i = 0`, SNIPS is `0`. Round SNIPS to 6 decimal places.

Do not substitute `N` for `Σ w_i` in the denominator.

The primary report field `metrics.policy_value` MUST equal SNIPS (not IPS).

## Stage G — Doubly robust (`dr_mode = "residual_direct"`)

```
DR = mean_i( w_i * (r_i - q̂_i) + direct_i )
```

Round DR to 6 decimal places.

Do not use an IPS-only path and do not add `mean(direct)` onto IPS as a
surrogate.

## Stage H — Effective sample size

```
ESS = (Σ_i w_i)^2 / (Σ_i w_i^2)
```

If `Σ w_i^2 = 0`, ESS is `0`. Round ESS to 6 decimal places.

Do not use `N / max(w)` or other shortlist heuristics.

## Stage I — Confidence half-width

Let `x_i = w_i * r_i` and `μ = mean(x_i)` (= IPS before rounding).

```
var = mean_i( (x_i - μ)^2 )
ci_half_width = 1.96 * sqrt(var / N)
```

If `N = 0`, `ci_half_width = 0`. Round to 6 decimal places.

## Stage J — Policy score and serve gate

```
policy_score = max(0, round(100 - 80 * abs(1 - ESS/max(N,1)) - 200 * ci_half_width, 2))
serve_block = (ESS < ess_threshold) OR (ci_half_width > ci_threshold) OR (policy_value < value_floor)
```

Release thresholds:

- `ess_threshold = 50.0`
- `ci_threshold = 0.12`
- `value_floor = 0.15`

## Stage K — Per-arm diagnostics

Emit one arm object per action in the schema action list, sorted ascending by
`action` string.

For each action `a`:

- `n` = count of retained events with that action
- If `n = 0`: `included=false`, `exclude_reason="EMPTY_ARM"`, zeroed metric
  fields, `flagged=false`, `flag_reason=""`
- Otherwise:
  - `included=true`, `exclude_reason=""`
  - `mean_weight = mean(w)` over events with action `a` (round 6)
  - `ips_contrib = (Σ w*r for action a) / N` (round 6)
  - `mean_reward = mean(r)` over events with action `a` (round 6)
  - If `mean_weight > clip_max * 0.9`: `flagged=true`,
    `flag_reason="HEAVY_WEIGHT"`; else unflagged

`window.arms_evaluated` counts included arms. `window.arms_flagged` counts
flagged included arms.

## Stage L — Calibration identities

The `calibration` object must stamp the identities actually used for scoring:

| key | value |
|-----|-------|
| `clip_max` | `10.0` |
| `propensity_floor` | `0.01` |
| `ess_threshold` | `50.0` |
| `ci_threshold` | `0.12` |
| `value_floor` | `0.15` |
| `estimator` | `"snips"` |
| `weight_mode` | `"clipped_ratio"` |
| `dr_mode` | `"residual_direct"` |
| `aggregate` | `"macro"` |

## Stage M — Config precedence

Primary `/app/config/eval.json` supplies `schema_version`, `policy_source`,
`cutoff_unix`, `eval_window_sec`, and `legacy_reconcile`. Overlay profiles
under `/app/config/overlays/` and governance degraded-mode fallbacks must not
override evaluation thresholds, clip/floor identities, or force
`legacy_reconcile=true` for this compliance evaluation.

Primary values for this release:

- `schema_version = "1.0"`
- `policy_source = "offline-bandit-ips-v1"`
- `legacy_reconcile = false`

## Stage N — Output schema

`/app/output/ips_eval.json` top-level keys:

- `schema_version` (string)
- `policy_source` (string)
- `window` object with `cutoff_unix`, `eval_window_sec`, `eval_rows`,
  `floor_excluded`, `arms_evaluated`, `arms_flagged`
- `metrics` object with `policy_value`, `ips`, `snips`, `dr`, `ess`,
  `ci_half_width`, `policy_score`, `serve_block`
- `arms` array (see Stage K)
- `calibration` object (see Stage L)
