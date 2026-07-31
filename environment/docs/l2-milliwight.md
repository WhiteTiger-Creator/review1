# Ridge scorer contract

## Design matrix

For each labeled bout used in training:

- Read label `y` from the labels JSONL (`bout_id`, `y`) where `y ∈ {0,1}`.
- Let `x` be the 12-D feature vector.
- Row of `X` is `[1, x0, x1, …, x11]` (intercept column first). Length 13.

Training uses every label whose `bout_id` exists in the active capture bank. Sort training rows by `bout_id` ascending.

## Closed-form solve

Policy field `ridge_lambda` is a positive integer `λ`.

Solve `w` in `R^13` for

`(XᵀX + λ I) w = Xᵀ y`

with these exact rules:

1. Build `A = XᵀX` using integer arithmetic into float64.
2. Add `λ` to every diagonal entry of `A` **including the intercept diagonal**.
3. Solve the 13×13 system with Gaussian elimination and partial pivoting in float64.
4. Round each weight to nearest integer milliwight: `w_milli[i] = floor(w[i] * 1000 + 0.5)` (half away from zero via standard `math.Round` semantics on `w[i]*1000`).

Persist `/app/qualitycast/ridge_weights.json`:

```json
{
  "dim": 13,
  "lambda": <policy ridge_lambda>,
  "w_milli": [13 integers],
  "train_bout_ids": ["..."]
}
```

## Scoring

Score `s_milli = w_milli·[1000, 1000*x0, …]` then `s = s_milli / 1_000_000` in float64.
Predicted label `ŷ = 1` iff `s >= 0.5`, else `0`.
