Per-lane rolling pedestal window with epoch-frozen pulser weights.

# Rolling pedestal model

The crate interleaves pedestal acquisitions with pulser acquisitions so that the
pedestal can be tracked while it moves. The reduction tracks it the same way: a pulser
observation is corrected and weighted by the pedestal population that existed **at that
observation's own place in documented process order**, never by a run-average pedestal
and never by a population containing pedestals recorded later.

Constants used here: `PEDESTAL_K = 8`, `PEDESTAL_P = 4`, `MAD_SCALE = 1.4826`,
`PEDESTAL_VAR_FLOOR = 1.0`, `NOISE_SIGMA_LIMIT = 12.0`.

## The rolling window

Every lane owns one window holding the most recent `PEDESTAL_K` reduced pedestal
charges for that lane. As the merged frame list is walked in documented process order, a
reduced pedestal frame appends its integrated charge to its lane's window; when the
window is full the oldest charge is discarded. It is a fixed-length FIFO, never a
growing list and never a buffer that resets on a threshold.

Saturated pedestal frames are rejected before this point (`waveform.md`) and are
not appended. Pulser charges never enter the window, and windows are strictly per lane:
one lane's pedestal population is never pooled with another's.

## The epoch counter

Each lane also carries an epoch counter, starting at zero and incremented by one every
time that lane appends a pedestal charge. The counter is the identity of the lane's
current pedestal population: two pulser observations carry the same epoch exactly when
no pedestal frame for that lane was processed between them, which is exactly when they
were corrected against the same window contents.

The epoch is a label, not a time. It is what the fit uses to group observations that
share a pedestal error (`gls_calibration.md`), so it must advance on every pedestal, not on a
fixed schedule and not only when the window's contents happen to change value.

## The pedestal state

At the moment a pulser frame is processed, its lane's window is summarized. With
`c[1..n]` the charges currently held:

```
pedestal_charge   = median(c[1..n])
pedestal_sigma    = MAD_SCALE * median(|c[j] - pedestal_charge|)
pedestal_variance = max(pedestal_sigma^2, PEDESTAL_VAR_FLOOR)
size              = n
epoch             = the lane's epoch counter
```

A median and a scaled MAD are used so that a single wild pedestal frame cannot drag
either the location or the scale. The variance floor keeps a perfectly repeatable
pedestal population from contributing zero variance, which would make the fit
covariance singular; note that the floor applies to the variance used for weighting,
while the published `pedestal_sigma` is the unfloored scale estimate.

A lane with an empty window reports `pedestal_charge = 0`, `pedestal_sigma = 0`,
`pedestal_variance = PEDESTAL_VAR_FLOOR`, and `size = 0`.

## Admitting a pulser observation

A reduced pulser frame is tested against its lane's current state, in this order:

1. **Availability.** If `size < PEDESTAL_P` the pulser is rejected and increments
   `frames_rejected_no_pedestal`. Pulsers that arrive before the crate has recorded
   enough pedestals are unusable, not merely unweighted: they are never admitted with a
   provisional, default, or borrowed pedestal.
2. **Noise.** If `pedestal_sigma > NOISE_SIGMA_LIMIT` the population is too dispersed to
   subtract. The pulser is rejected, increments `frames_rejected_noisy`, and the lane
   records that it lost an observation this way.
3. **Admission.** Otherwise the frame becomes an observation and increments
   `frames_accepted`.

## Pedestal subtraction and weighting

An admitted observation carries:

```
level    = pulser_level of the frame
time     = timestamp_ns of the frame, converted to seconds
charge   = gate charge - coverage * pedestal_charge
variance = charge_var + coverage^2 * pedestal_variance
epoch    = the lane's epoch counter at this moment
```

The pedestal is scaled by `coverage` because the pedestal charge is measured over the
complete `GATE_WIDTH` gate while a clipped pulser gate integrated only `coverage` of
that many samples. Subtracting the full pedestal from a clipped gate over-subtracts, and
the same factor squared propagates the pedestal variance into the observation.

These four quantities are **frozen** at admission. Pedestal frames arriving later change
the window for subsequent observations only; they never retroactively re-correct or
re-weight an observation already admitted. An implementation that gathers a lane's
pulsers first and subtracts a final pedestal afterwards produces uniform weights, a
single epoch, and the wrong gain.

The noise test is evaluated **per observation**, against the state current at that
observation, and is never a per-lane verdict computed once. On a lane whose pedestal is
briefly unstable, early observations are rejected as noisy while later ones are admitted
normally: the lane recovers as soon as enough clean pedestals have rolled through the
window to bring `pedestal_sigma` back under the limit. Latching a lane into a noisy state
on first sight discards real observations.

## Lane outcomes

Every lane named by any merged frame gets a row in the published table, whatever became
of its frames. The number of observations a lane admitted, and the number of pulsers it
lost to the noise test, both feed the fit's classification of the lane (`gls_calibration.md`).

## Published pedestal columns

Each lane row publishes `pedestal_charge` and `pedestal_sigma` taken from that lane's
state **as of the end of the run**, after every frame has been processed. A lane that
never contributed a pedestal frame publishes `0.0` for both. These are diagnostics of
the lane's final pedestal; they are not the values used to correct any particular
observation, since each observation used the state current at its own process time.
