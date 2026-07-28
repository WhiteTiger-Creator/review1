# Specimen vectors

Each specimen has id, ticks, target_energy, cohort (learning|reserved).

Design columns: [1, x1, x2, x3, x1², x2², x3²] where x1=mean(ticks), x2=max(ticks),
x3=population std(ticks) with divisor n (not n-1). Apply trunc_decimals via
`/app/docs/trunc-decimals-contract.md` to each column. Do not emit cross terms x1·x2.
The exact `column_names` array, in that order, is
`["intercept", "mean", "max", "std", "mean_sq", "max_sq", "std_sq"]`.

Scheme hwml.design/v1. Rows sorted ascending by id. Echo workbook `policy_epoch`
onto the design matrix and design vault objects.

Each design/vault row object carries exactly these fields: `id` (specimen id
string), `cohort` (`learning` or `reserved`), `columns` (the seven-element
expanded feature array above), and `target_energy` (float label, untruncated).
---

Scheme id: hwml.design/v1
