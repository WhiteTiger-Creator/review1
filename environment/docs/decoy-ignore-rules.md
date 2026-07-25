# Decoy ignore rules

Paths under /app/decoy and /app/sidecut are non-authoritative. Do not import them from latchml hot-path modules.

In particular:

- /app/sidecut/mean_predictor.py is a flat mean label toy, not the OLS forecast path.
- /app/decoy/ridge_always.py applies a ridge penalty; the lab contract is plain OLS (ridge_lambda workbook keys must be ignored).
- /app/featbank and /app/metriclab helpers may use unrelated ceiling names; workbook MAPE/R² ceilings in /app/docs/mape-r2-metric-contract.md govern promotion.
