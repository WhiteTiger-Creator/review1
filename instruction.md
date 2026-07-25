Implement the constrained offline graph-safety evaluator in /app/estimate.R.

Read the relational bank-policy logs, fit regularized cluster transition graphs, select the regularizer by nested held-cluster transition validation, and evaluate every policy using robust edge values and its minimum directed simple-cycle mean. Apply the return, safety, and effective-sample-size rules, then produce every required one-cluster or multi-cluster deletion refit.

/app/run.sh invokes the estimator with an optional data directory and output path. The binding schemas, graph model, cross-validation rule, cycle definition, feasibility and fallback ordering, deletion certificate, output columns, precision, and audit signature are defined in /app/docs/OUTPUT-CONTRACT.md.

All outputs must be derived at runtime. Inputs may contain opaque state and policy identifiers, extreme importance ratios, reordered records and headers, missing empirical edges, boundary cases, and irrelevant columns. Internet access is unavailable; only base R is guaranteed.
