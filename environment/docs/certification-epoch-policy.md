# Certification epoch annex

When graph.json certification_epoch equals 2, bound comparison tightens: a layer passes only if measured_drift is strictly less than drift_bound (not equal). When certification_epoch is any other value, a layer passes when measured_drift is less than or equal to drift_bound.

measured_drift used for the comparison is recomputed from the persisted ref and quant interval endpoints after those endpoints are written with six digits after the decimal (printf-style %.6f), matching /app/docs/bound-workspace-snapshot.md. Do not compare pre-persistence floating values against the ceiling.
