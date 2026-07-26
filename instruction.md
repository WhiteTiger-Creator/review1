The required deliverable is /app/estimate.R, an offline bank-policy safety evaluator.

It must read the relational inputs, tune one global transition-and-uncertainty candidate by held-cluster validation, evaluate exposure-weighted policy return and directed-cycle safety under cluster covariance, and produce the complete cluster-deletion stability certificate.

/app/run.sh invokes the evaluator with an optional data directory and output path. The input schemas, fitted graph, support rule, validation objective, cycle functional, feasibility ordering, deletion refits, output columns, numerical decisions, and audit signature are defined in /app/docs/OUTPUT-CONTRACT.md.

Every result must be derived at runtime. Inputs can contain opaque identifiers, extreme importance ratios, reordered rows and headers, missing empirical edges, boundary values, irrelevant columns, and one- or two-cluster deletion requirements. Internet access is unavailable, and only base R is guaranteed.
