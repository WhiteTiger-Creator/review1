# Teaching-evaluation model output guide

The analysis reads only `/app/data/train.csv` and `/app/data/score.csv` and writes exactly thirteen artifacts under `/app/outputs`. Use `task_name = "tae-multiclass-cv-audit"`, `source_dataset = "UCI Teaching Assistant Evaluation Dataset"`, `random_state = 20260713`, and class order `eval_low`, `eval_medium`, `eval_high`. The original predictors, in order, are `native_english_speaker`, `course_instructor`, `course_id`, `summer_or_regular`, and `class_size`. Treat the first four as categorical and `class_size` as numeric. Exclude `row_id`, `split_role`, and `evaluation_class`.

## Preparation and model selection

Learn every preprocessor from the rows used by that fit. For `class_size`, compute the mean from raw training values while ignoring missing entries, use zero only when the entire column is missing, impute every corresponding frame with that mean, and compute the sample standard deviation on the imputed training values. Replace a zero or undefined scale with one and standardize with the training center and scale.

For each categorical predictor, map missing or blank training values to `__missing__`. Its vocabulary is R's character sort of the union of mapped training values, `__missing__`, and `__other__`. Map a nonmissing value absent from that vocabulary to `__other__`. Encode every vocabulary level with its own indicator named `<predictor>_<make.names(level)>`; retain all indicator columns. Categorical sorting is lexicographic, so `"10"` precedes `"2"`.

Fit `nnet::multinom` with an intercept, all prepared columns, row weights `n_train / (3 * class_count_for_that_row)`, `trace = FALSE`, `maxit = 1000`, `MaxNWts = 50000`, and `decay = C`. Candidate C values are `0.01`, `0.03`, `0.1`, `0.3`, `1`, `3`, `10`, and `30`, in that order.

Create five fit-only folds. Within each class in published class order, sort rows by `row_id`; rank `r` receives fold `((r - 1) %% 5) + 1`. For candidate index `i` and fold `f`, call `set.seed(random_state + 100 * i + f)` immediately before fitting. Relearn preprocessing and weights from the other four folds and score the held-out fold. Select the smallest candidate whose full-precision mean holdout log loss is within `1e-10` of the minimum. Validation labels do not influence selection. For the final all-fit model, call `set.seed(random_state + 9000 + selected_candidate_index)` immediately before fitting.

Multiclass log loss is the row mean of `-log(max(probability_of_actual_class, 1e-15))`. For each class, precision, recall, and F1 are zero when their denominator is zero. Macro F1 and balanced accuracy are the arithmetic means of per-class F1 and recall over all three classes; weighted F1 is support-weighted. Predicted classes use the largest full-precision probability with class-order tie breaking.

## Artifacts

`metrics.json` contains exactly `task_name`, `n_fit`, `n_validation`, `n_score`, `classes`, `selected_c`, `selected_cv_mean_log_loss`, `selected_cv_log_loss_sd`, `validation_macro_f1`, `validation_weighted_f1`, `validation_balanced_accuracy`, `validation_accuracy`, `validation_log_loss`, `fit_oof_macro_f1`, and `fit_oof_log_loss`. Counts are integers; other numeric values use six decimals.

`candidate_results.csv` has one row per candidate in grid order and columns `candidate_c`, `cv_mean_log_loss`, `cv_log_loss_sd`, `cv_mean_macro_f1`, and `is_selected`. Aggregate full-precision fold values; metrics use six decimals and the flag is integer 0 or 1.

`fit_cv_results.csv` uses candidate-major then fold-major order and columns `candidate_c`, `fold_id`, `training_rows`, `holdout_rows`, `holdout_log_loss`, `holdout_macro_f1`, `holdout_accuracy`. Counts are integers and metrics use six decimals.

`fit_oof_predictions.csv` contains every fit row once, sorted by `row_id`, using the selected candidate model that excluded that row's fold. Its columns are `row_id`, `fold_id`, `actual_class`, `predicted_class`, `prob_eval_low`, `prob_eval_medium`, `prob_eval_high`, `log_loss_component`, and `is_correct`. Probabilities and log-loss components use eight decimals; IDs, fold, and correctness are integer or string fields as appropriate.

`fold_preprocessing_summary.csv` contains one row per fold for the selected candidate, in fold order, with `fold_id`, `training_rows`, `holdout_rows`, `class_size_missing_count`, `class_size_center`, `class_size_sample_sd`, `instructor_level_count`, and `course_level_count`. Counts are integers and preparation values use eight decimals. Level counts include the mandatory `__missing__` and `__other__` levels.

`predictions.csv` contains score rows only, sorted by `row_id`, with `row_id`, `predicted_class`, `prob_eval_low`, `prob_eval_medium`, `prob_eval_high`. Round each raw class probability independently to eight decimals.

`validation_confusion_matrix.csv` contains `actual_class`, `predicted_class`, `n` for all nine ordered class pairs, actual class as the outer loop and predicted class as the inner loop.

`validation_class_report.csv` contains `class`, `support`, `precision`, `recall`, `f1`, `mean_probability` in class order. `mean_probability` is that class's mean predicted probability among validation rows whose actual class is the same, or zero when support is zero. Non-count values use six decimals.

`validation_confidence_deciles.csv` starts from validation rows sorted by descending full-precision maximum probability and ascending `row_id` for ties. Rank `r` among `n` rows belongs to decile `floor((r - 1) * 10 / n) + 1`. Emit deciles 1 through 10 with `decile`, `row_count`, `accuracy`, `mean_confidence`, `mean_margin`, and `mean_log_loss_component`. Margin is the largest minus second-largest full-precision probability. Empty deciles use zero summaries; non-count values use six decimals.

`score_course_counterfactual.csv` audits the final model without refitting. For every level in the final `course_instructor` vocabulary order, replace `course_instructor` in every raw score row with that level, apply the unchanged final preprocessor, and predict. Emit `course_instructor_level`, `encoded_column`, `predicted_eval_low_count`, `predicted_eval_medium_count`, `predicted_eval_high_count`, `changed_class_count`, `mean_prob_eval_low`, `mean_prob_eval_medium`, `mean_prob_eval_high`, and `mean_total_variation`. Total variation is one half of the rowwise sum of absolute class-probability changes from baseline score predictions. Count fields are integers; means use six decimals.

`model_term_importance.csv` contains one row per original predictor in original order with `feature`, `design_term_count`, `l2_norm`, `normalized_importance`, and `max_abs_coefficient`. Treat the omitted baseline-class coefficients as zero, group final model coefficients by original predictor, and exclude the intercept. `l2_norm` is the square root of the sum of squared coefficients in that group. `normalized_importance` is the group's unrounded L2 norm divided by the sum across the five groups, or zero if the sum is zero. Numeric summaries use eight decimals without post-rounding correction.

`preprocessing_summary.csv` contains one row per original predictor in order and columns `feature`, `feature_type`, `fit_missing_count`, `validation_missing_count`, `score_missing_count`, `fit_center`, `fit_sample_sd`, and `level_count`. For categorical rows, center is zero and scale is one; for the numeric row, level count is zero. Numeric summaries use eight decimals and counts are integers.

`model_manifest.json` contains exactly `task_name`, `feature_columns`, `categorical_columns`, `numeric_columns`, `excluded_columns`, `fit_rows`, `validation_rows`, `score_rows`, `candidate_grid`, `selected_c`, `cv_folds`, `random_state`, `class_order`, `model_family`, `source_dataset`, `design_columns`, and `artifact_files`. Row counts and fold count are integers. Use model family `class_weighted_multinomial_ridge`; preserve the published candidate, class, feature, design-column, and artifact ordering.

All CSV files include headers, omit row names, and use the exact column order above. Write JSON with `jsonlite::write_json(..., auto_unbox = TRUE, pretty = TRUE, digits = NA)`.
