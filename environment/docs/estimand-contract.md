# Estimand contract

## Quantity to report

Some patients in this registry never relapse; they remain event-free permanently. For a
given therapy world, the long-term event-free probability is the share of patients who
never relapse when that therapy is applied to everyone. The quantity to report is the
difference in that probability between the world in which every patient receives the newer
therapy and the world in which every patient receives the standard therapy, taken as newer
minus standard, so that a therapy leaving more patients permanently event-free yields a
positive value.

The difference is standardized to this registry's own distribution of the two baseline
flags (`stage_high`, `marker_high`): it is the average, over that distribution, of the
newer-minus-standard difference in long-term event-free probability within each flag group.

## Identifiability

Which therapy a patient received was not decided at random. Each of the two baseline flags
and the continuous baseline index is associated both with therapy receipt and with whether a
patient relapses in the long run, so the two therapy arms are not comparable as observed;
the reported quantity is the therapy contrast that would hold once the arms are made
comparable on these recorded pre-therapy characteristics. A patient still under observation
without a recorded relapse is not yet known to be permanently event-free — a relapse could
still have followed had observation continued. Within every baseline-flag group and under
either therapy, observation runs long enough that the group's long-term event-free
probability is identified from its records.

## Invariance to the time unit

The reported quantity does not depend on the unit in which times are recorded. If every
recorded time — the enrolment month, the follow-up time, and the site administrative cutoff
— is multiplied by a common positive constant, so that the administrative window is
preserved, the reported number is unchanged. It is a property of the ordering of relapse
events and of which observations are censored, not of the numeric scale on which the times
happen to be recorded.

## Determinism

The program is rerun on freshly drawn registries. It must recompute the reported number
from whatever records the data directory holds and must not depend on a stored constant;
the same records must always yield the same number.
