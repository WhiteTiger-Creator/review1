# Output contract

Write the analysis as an R program at `/app/analysis.R`. When run, it must read the
cohort observations from the directory named by the environment variable `CAUSAL_DATA_DIR`,
falling back to `/app/data` when that variable is unset.

The program writes `/app/estimate.json` containing a single JSON object with exactly one
key, `estimate`, whose value is the reported difference as a finite number. For example:

```json
{"estimate": 0.12}
```

No other keys, files, or console output are required. The value must be a plain number,
not a string, and must be finite. Running the program twice on the same records must
produce the same number.
