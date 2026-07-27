# Stylus Policy Digit Contract

The task is a policy-weighted handwritten digit prediction problem. Training rows are labeled. Evaluation rows have the same public fields but with the digit label withheld.

The trajectory data are derived from the UCI Pen-Based Recognition of Handwritten Digits dataset, DOI 10.24432/C5MG6K, CC BY 4.0. The original released training and writer-independent test split are retained; policy fields and stable record ids are constructed from public stroke geometry.

Input files:

- `/app/data/training_digits.csv`
- `/app/data/evaluation_digits.csv`
- `/app/data/split_manifest.csv`

Coordinate columns `x1,y1,...,x8,y8` are integer pen positions scaled from 0 through 100. The eight points preserve their stroke order. `record_id` is the stable key.

The constructed capture action is one of `compact_trace`, `long_sweep`, or `rising_tail`. It is derived from public stroke geometry and is already supplied in both input files. `behavior_propensity` is the probability assigned by the logging capture policy. `target_probability` is the deployed capture-policy probability for the same action. `policy_weight` is `target_probability / behavior_propensity` and should be treated as the row's target-policy importance weight for fitting and evaluation.

The training file adds `digit_label`, an integer from 0 through 9. The evaluation file intentionally omits that column. The released evaluation split is writer-independent relative to the training split.

Write `/app/outputs/digit_probabilities.csv` with exactly these columns:

`record_id,p_0,p_1,p_2,p_3,p_4,p_5,p_6,p_7,p_8,p_9`

Include every evaluation id exactly once. Do not include training ids. Each `p_k` is the predicted probability that the hidden digit is `k`. Values must be finite, lie between 0 and 1 inclusive, and sum to 1 by row within 0.000001.

Low-behavior-propensity rows are evaluation rows with `behavior_propensity <= 0.4`. The verifier separately checks predictive quality on those rows, so the model should not discard or downweight them as unreliable outliers.

Verifier-held labels score policy-weighted multiclass log loss, macro recall, and Brier score. Overall thresholds are log loss below 0.140, macro recall above 0.955, and Brier below 0.060. Low-behavior-propensity thresholds are 0.100, 0.965, and 0.035. Compact-trace thresholds are 0.180, 0.930, and 0.080. For the confusable digit set 1, 5, 7, and 9, thresholds are 0.170, 0.935, and 0.075 overall and 0.245, 0.905, and 0.110 on compact-trace rows.
