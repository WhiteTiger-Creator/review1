# Tare calibration contract

From `tare_runs.json`, retain only runs with `wind_on == false`.

Let \(N\) be the retained count (\(N \ge 2\) for facility campaigns).

\[
\bar{F}_x = \frac{1}{N}\sum F_x,\quad
\sigma_{F_x} = \sqrt{\frac{1}{N-1}\sum (F_x-\bar{F}_x)^2}
\]

(and likewise for `Fz`, `My`).

Do not include `wind_on == true` rows in means or sample standard deviations. Emit `tare_run_count = N` in `calibration_summary.json`.
