# Grouped evaluation audit

`bin/weka-cv-audit` loads an ARFF dataset with Weka and evaluates a nearest-centroid classifier by holding out one collection group at a time. The report contract is in `docs/evaluation-contract.md`.

Run the bundled example with:

```bash
/app/bin/weka-cv-audit \
  --data /app/examples/sites.arff \
  --class species --id sample_id --group site \
  --top 2 \
  --out /app/report.json
```
