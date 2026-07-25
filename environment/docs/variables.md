# Variables measured in the registry

The observations live under the directory named by `CAUSAL_DATA_DIR` (default `/app/data`)
and come from an observational oncology registry. Each patient carries a `patient_id` that
identifies them wherever they are observed, and each patient enrolled at a site carrying a
`site_id`. The registry measured three kinds of observation: what was recorded about a
patient at enrolment, what was observed about that patient during follow-up, and when each
site closed.

## Enrolment observations (`enrollment.csv`)

One record per patient, capturing baseline characteristics measured at enrolment before
therapy was chosen. Each record gives the patient's `patient_id`, the `site_id` of the site
where they enrolled, and their `enroll_month` (calendar month of enrolment, counted from the
registry's start). It records the `therapy` the patient received, `newer` or `standard`; two
fixed baseline flags, `stage_high` (disease stage, `1` if high else `0`) and `marker_high`
(biomarker, `1` if high else `0`); and `baseline_index`, a continuous baseline lab index
measured before the therapy was chosen.

## Follow-up observations (`followup.csv`)

One record per patient, capturing what was observed during follow-up. Each record gives the
patient's `patient_id`, `months_observed` (months from that patient's enrolment to the end
of their observation), and `outcome`, which is `relapse` if a relapse was observed at
`months_observed` and `censored` otherwise.

## Site closing dates (`site_calendar.csv`)

One record per registry site, capturing when observation closed. Each record gives the
`site_id` and `administrative_cutoff_month`, the calendar month at which that site closed
follow-up.

## Timeline and observation

Both baseline flags are fixed characteristics measured at enrolment, before the therapy
was chosen. A patient is observed from enrolment until either a relapse is recorded or
observation ends without one; observation can end because the site reached its
administrative cutoff or because the patient was lost to follow-up earlier. A record marked
`censored` means only that no relapse had been recorded by `months_observed`; it does not
by itself say whether that patient would ever have relapsed.

A structural property of this registry holds across the records: within every combination
of the two baseline flags and under either therapy, some patients are observed past the
month after which no further first relapses occur anywhere in that group. In other words,
in each such group the observation window extends beyond the last time at which any patient
in the group first relapses.
