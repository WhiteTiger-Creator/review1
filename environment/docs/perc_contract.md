# Averaged perceptron training contract

Offline trainer under `/app/environment` folds feature packs, trains a binary
averaged perceptron, and publishes dual-slot model pages under `/app/var/model`.

## Feature pack merge

`manifest.json` lists pack paths under `packs`. Merge packs in **declaration
order**. Do not reorder by path name.

Each pack line is `name active` with `active` 0 or 1. Later packs override the
active bit for the same feature name. Inactive features do not participate in
scoring or updates. Shipped packs declare features named `color`, `shape`,
`bulk`, and `texture`.

## Averaged perceptron

Weights `w` and bias are the last plane. Accumulators `u` / `ubias` sum the last
plane after every accepted update. When `updates > 0`, the averaged plane is
`u[i]/updates` and `ubias/updates`.

Training margin for an example uses the **last** plane:
`margin = label * (bias + sum last_w[feat])`.

An update runs **only when margin <= 0**. On update: increment `updates`, add
`label` into each active feature weight present on the example and into bias,
then add the new last values into `u` / `ubias`.

When margin > 0, record `outcome=skip` with `reason=MARGIN_OK` and do not change
weights.

Prediction uses the **averaged** plane when `updates > 0`, otherwise the last
plane. `pred` is `+1` if score >= 0 else `-1`. Mispredicts record `outcome=deny`
and `reason=MISPRED`.

## Digests and fence

Model digest is FNV-1a 32-bit hex of:
`g=<generation>|u=<updates>|` then for each **active** feature in model order
`<name>:<avg_w six decimals>,` then `b=<avg_bias six decimals>`.

Fence is FNV-1a 32-bit hex of `<digest>|<generation>|<updates>`.

## Cut and delayed plane

`cut` advances `generation` by one. Prediction after cut still uses the averaged
plane (last plane may differ). This surfaces last-vs-average disagreement after
training has moved the last plane.

## Dual-slot model pages

`publish` writes standby then active under `/app/var/model`.
`tear` leaves torn `active.page` plus `active.page.partial`. The torn active
page header begins with `generation 0`. After a successful `recover`, the
partial marker is absent.
`recover` prefers standby when the partial marker is present, rewrites active
from recovered material, and sets `notes` to `had_partial` when the marker was
observed.

## Ledger

`/app/output/perc_ledger.json` uses schema `perc_model_v1` with `journal_path`,
`journal_generation`, `deny_count`, `updates`, and `runs`. Each run carries
`action`, `case_id`, `outcome`, `reason`, `epoch`, `pred`, `label`, `margin`,
`digest`, `fence`, `persist_id`, `carried`, `lineage_skew`, `notes`.
`persist_id` remains `0xA11E`.
