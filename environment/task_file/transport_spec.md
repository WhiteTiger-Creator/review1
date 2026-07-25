# Multicarrier Hall Transport Calibration Contract

Paths in this document are relative to the input and output directories passed to `/app/hall_transport`. The supplied directories are `/app/task_file/input_data/` and `/app/task_file/calibration/`.

## Input archive

`case_config.csv` has header `key,value`. It contains `residual_sigma_threshold`, `run_bias_sigma_threshold`, `combined_rms_max`, `longitudinal_rms_max`, `hall_rms_max`, `residual_p90_max`, `min_clean_fraction`, `reference_temperature_k`, `max_charge_imbalance`, `total_density_min_1e22_m3`, `total_density_max_1e22_m3`, `min_conductivity_share`, `min_mobility_ratio`, `max_activation_step_mev`, `max_field_scale_step`, `max_mean_longitudinal_offset_uohm_m`, `max_mean_hall_offset_uohm_m`, and `output_decimals`.

`carriers.csv` has header `carrier_id,band_index,charge_sign,density_min_1e22_m3,density_max_1e22_m3,prior_density_1e22_m3,mobility_min_cm2_vs,mobility_max_cm2_vs,prior_mobility_cm2_vs,activation_min_mev,activation_max_mev,prior_activation_mev,alpha_min,alpha_max,prior_alpha`. `band_index` is a positive integer unique across the archive. `charge_sign` is exactly `-1` or `1`. Carrier row order is canonical and is also the mobility and activation-smoothness order.

`runs.csv` has header `run_id,temperature_k,field_scale_min,field_scale_max,prior_field_scale,longitudinal_offset_min_uohm_m,longitudinal_offset_max_uohm_m,prior_longitudinal_offset_uohm_m,hall_offset_min_uohm_m,hall_offset_max_uohm_m,prior_hall_offset_uohm_m`. Run row order is canonical and is the field-scale smoothness order.

`observations.csv` has header `observation_id,run_id,field_t,observed_longitudinal_uohm_m,observed_hall_uohm_m,sigma_longitudinal_uohm_m,sigma_hall_uohm_m,use_flag`. `observation_id` is an integer. Both sigma values are positive. A `use_flag` of `0` reports the row but excludes it from residual-quality gates.

`prior_flags.csv` has header `observation_id,reason`. Its reason text is not copied to output. `input_hashes.json` contains SHA-256 hashes of the five CSV files and is an integrity aid only.

## Transport model

Let `T0` be `reference_temperature_k`. For carrier `k`, the submitted reference density `n0` is expressed in `1e22 m^-3`, reference mobility `mu0` is in `cm^2 V^-1 s^-1`, activation energy `E` is in meV, and mobility exponent is `alpha`. At temperature `T`:

`n_k(T) = n0 * 1e22 * exp(-(E / 0.08617333262145) * (1/T - 1/T0))`

`mu_k(T) = mu0 * 1e-4 * (T/T0)^(-alpha)`

For an observation in run `r`, `B = field_t * field_scale_r`. With elementary charge `e = 1.602176634e-19 C` and carrier sign `s_k`:

`sigma_xx = e * sum_k(n_k * mu_k / (1 + (mu_k * B)^2))`

`sigma_xy = e * sum_k(s_k * n_k * mu_k^2 * B / (1 + (mu_k * B)^2))`

`rho_xx_uohm_m = 1e6 * sigma_xx / (sigma_xx^2 + sigma_xy^2) + longitudinal_offset_r`

`rho_xy_uohm_m = -1e6 * sigma_xy / (sigma_xx^2 + sigma_xy^2) + hall_offset_r`

The longitudinal and Hall normalized residuals are `(modeled - observed) / sigma` for their respective channels. Every calculation and emitted number must be finite, each density and mobility must be positive, and `sigma_xx^2 + sigma_xy^2` must be positive.

## Simultaneous final-state gates

Every emitted carrier and run parameter must stay within its matching inclusive bounds. The following gates apply independently and simultaneously to the complete final parameter vector after six-decimal canonicalization; satisfying one never suppresses another.

At `T0`, `total_density_1e22_m3` is the sum of reference carrier densities and must lie in the configured inclusive interval. `charge_imbalance` is `abs(sum_k(charge_sign_k * density_k)) / total_density` and must not exceed `max_charge_imbalance`.

The reference conductivity contribution of a carrier is `density_k * mobility_k`. Its `conductivity_share` is that contribution divided by the sum over all carriers. Every carrier share must be at least `min_conductivity_share`; `minimum_conductivity_share` is the smallest share.

For every adjacent pair in carrier input order, `mobility_i / mobility_(i+1)` must be at least `min_mobility_ratio`, so mobility must decrease in that order. Every absolute adjacent activation-energy difference must be at most `max_activation_step_mev`. `minimum_mobility_ratio` and `maximum_activation_step_mev` summarize these checks; for fewer than two carriers they are `0.0`.

For every adjacent pair in run input order, the absolute field-scale difference must be at most `max_field_scale_step`; for fewer than two runs, `maximum_field_scale_step` is `0.0`. The absolute arithmetic mean of all submitted longitudinal offsets and the absolute arithmetic mean of all submitted Hall offsets must not exceed their configured maxima.

Base-eligible observations have neither `excluded_observation` nor `prior_flag`. Longitudinal RMS and Hall RMS use their corresponding normalized residuals over base-eligible observations. Combined RMS is the square root of the mean of both squared channel residuals, with both channels weighted equally. Residual p90 is the nearest-rank 90th percentile of `sqrt((longitudinal_residual^2 + hall_residual^2) / 2)` over base-eligible observations. These four metrics must not exceed their configured maxima. Each RMS and p90 is `0.0` for an empty set.

Clean fraction is `clean_observations / base_eligible_observations` and must be at least `min_clean_fraction`; it is `1.0` when the denominator is zero.

## Findings

Findings are additive and emitted in this exact order: `excluded_observation`, `prior_flag`, `longitudinal_outlier`, `hall_outlier`, `run_bias`.

`excluded_observation` applies when `use_flag` is `0`. `prior_flag` applies when the observation is listed in `prior_flags.csv`. Both earlier findings appear when both apply. If either applies, do not evaluate any of the three residual findings.

For each base-eligible observation, `longitudinal_outlier` and `hall_outlier` independently apply when the absolute corresponding normalized residual is greater than `residual_sigma_threshold`; both may apply. For `run_bias`, first compute the median combined residual magnitude among all base-eligible observations in the same run, using `sqrt((longitudinal_residual^2 + hall_residual^2) / 2)`; an empty-run median is `0.0`. `run_bias` applies when that observation's combined magnitude differs from the run median by more than `run_bias_sigma_threshold`. It is evaluated independently of both channel findings. A base-eligible observation is clean only when it has none of the three residual findings. Excluded or prior-flagged observations are not clean and are not in the clean-fraction denominator.

## Output files

All submitted carrier and run parameters use ordinary six-decimal formatting such as C `printf("%.6f")`. Those emitted values are the canonical inputs when constraints, modeled values, residuals, findings, and summaries are recomputed. JSON numeric values must be numbers, not numeric strings, booleans, NaN, or Infinity.

`transport_parameters.json` has exactly the keys `reference`, `rounding`, `carriers`, `runs`, and `constraints`. `reference` is exactly `"carrier input order and run input order"`. `rounding` is exactly `{"carrier_parameters":6,"run_parameters":6,"modeled_uohm_m":6,"residual_sigma":6}`.

`carriers` follows carrier input order. Every object has exactly `carrier_id`, `band_index`, `charge_sign`, `density_1e22_m3`, `mobility_cm2_vs`, `activation_mev`, and `alpha`. `runs` follows run input order. Every object has exactly `run_id`, `temperature_k`, `field_scale`, `longitudinal_offset_uohm_m`, and `hall_offset_uohm_m`.

`constraints` has exactly `charge_imbalance`, `total_density_1e22_m3`, `minimum_conductivity_share`, `minimum_mobility_ratio`, `maximum_activation_step_mev`, `maximum_field_scale_step`, `mean_longitudinal_offset_uohm_m`, and `mean_hall_offset_uohm_m`. The two mean-offset fields retain their signed arithmetic means; their gates use absolute values.

`observation_residuals.jsonl` contains one object per input observation sorted by numeric `observation_id`. Each object has exactly `observation_id`, `run_id`, `field_t`, `modeled_longitudinal_uohm_m`, `observed_longitudinal_uohm_m`, `longitudinal_residual_sigma`, `modeled_hall_uohm_m`, `observed_hall_uohm_m`, `hall_residual_sigma`, and `findings`. Modeled values are rounded to six decimals. Each residual may be computed from the unrounded modeled value or its emitted six-decimal value; an absolute difference up to `0.00001` from either replay is accepted. `findings` contains only applicable strings in the order above.

`transport_summary.json` has exactly `carrier_count`, `run_count`, `observations`, `scored_observations`, `clean_observations`, `combined_rms`, `longitudinal_rms`, `hall_rms`, `residual_p90`, `clean_fraction`, `charge_imbalance`, `total_density_1e22_m3`, `minimum_conductivity_share`, `minimum_mobility_ratio`, `maximum_activation_step_mev`, `maximum_field_scale_step`, `mean_longitudinal_offset_uohm_m`, `mean_hall_offset_uohm_m`, and `finding_counts`. `finding_counts` contains all five finding keys even when a count is zero. Numeric metrics are rounded to six decimals and are recomputed from canonical emitted parameters.

Compatible archives retain these files and rules while changing the scientific dimensions and inputs listed in the task request. The program must derive its calibration from the archive supplied on each run. If any final parameter, physical gate, or residual-quality gate fails, the program must return nonzero and must not leave any of the three named output files.
