Provide /app/estimate.R as an offline evaluator of bank policies.

For every case, infer importance-weighted transition support and learn edge utility responses from noisy, clustered observations. Tune one shared candidate by held-cluster prediction, then compare policies using downside-adjusted return, predictive calibration, and the minimum mean of every supported directed cycle.

Produce the complete stability certificate obtained by refitting after all required cluster deletions.

/app/run.sh invokes the evaluator with an optional data directory and output path. The relational schemas, predictive model, validation loss, graph and cycle rules, policy ordering, deletion refits, exact output, numerical decisions, and audit signature are defined in /app/docs/OUTPUT-CONTRACT.md.

All results must be derived at runtime. Inputs may reorder rows and headers, use opaque identifiers, omit empirical edges, include extreme importance ratios, or request one- and two-cluster deletions. Internet access is unavailable; only base R is guaranteed.
