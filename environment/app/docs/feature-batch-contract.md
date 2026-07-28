# Feature batch staging contract

`wtac-validate feature --campaign-dir DIR --work-dir DIR` must write work-dir staging artifacts before eval:

## feature_batch.json

Keys (exact): `campaign_id`, `q_inf_pa`, `alpha_rad`, `pairs`, `feature_epoch`.

- `q_inf_pa` is the freestream dynamic-pressure feature (`0.5 * rho * V^2`), never `pitot_q_pa` and never a pitot blend.
- `alpha_rad` is angle of attack in **radians** (`alpha_deg * pi / 180`), not degrees.
- `pairs` is the ordered list of paired upper/lower feature rows (`x_c`, `z_u`, `z_l`, `Cp_u`, `Cp_l`) used by model inference.
- `feature_epoch` is a positive integer matching `feature_ledger.json`.

## feature_ledger.json

Keys: `campaign_id`, `feature_epoch`, `eval_count`.

Each successful `feature` run increments `feature_epoch` by one for that work directory. `eval_count` starts at 0 and increments only after a successful `eval` that consumed the current epoch.
