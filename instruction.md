An oncology registry recorded patients who each received one of two therapies, a newer
therapy or a standard one. Therapy was not assigned at random: baseline characteristics
recorded before therapy — two flags, `stage_high` and `marker_high`, and a continuous
`baseline_index` — are each associated both with which therapy a patient received and with
whether that patient relapses. A real fraction of patients never relapse and stay event-free
permanently; the rest relapse at some time after enrolment. Observation ends at a relapse,
at a per-site administrative cutoff, or at an earlier loss to follow-up.

Report, as a single number, the difference in the long-term probability of never relapsing
between a world in which every patient is given the newer therapy and a world in which every
patient is given the standard one, taken as newer minus standard, standardized to this
registry's own distribution of the two baseline flags, and signed so that a therapy leaving
more patients permanently event-free comes out positive. A patient still under observation
with no recorded relapse is not yet known to be one who never relapses.

The reported number must be a property of the order in which relapses occur and of which
observations are censored, not of the units the times are written in: multiplying every
recorded time — the enrolment month, the follow-up time, and the site administrative cutoff
— by a common positive constant must leave it unchanged.

Estimate this quantity from the cohort held under the directory named by the environment
variable CAUSAL_DATA_DIR, falling back to /app/data when unset. The measured variables and
what each record captures are documented under /app/docs. Write your analysis as an R program
at /app/analysis.R that writes /app/estimate.json with a single numeric field named estimate.
Do not hardcode a number; the estimator is rerun many times on freshly drawn cohorts of this
size and must recompute the quantity from the observations the directory holds. Keep a single
run comfortably under twenty seconds on the two-CPU environment.
