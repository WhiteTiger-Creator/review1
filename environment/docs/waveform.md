Median/MAD baseline and clipped gate integration for PMT traces.

# Baseline estimation, charge integration, and frame quality

Applies to every frame that survives the merge, pedestal and pulser alike. Constants
used here: `PRE_TRIGGER = 32`, `INTEGRATION_HALF_WIDTH = 8`, `MAD_SCALE = 1.4826`,
`OUTLIER_K = 3.0`, `MIN_BASELINE_SAMPLES = 8`, `MIN_COVERAGE = 0.70`,
`PILEUP_FRAC = 0.35`, `PILEUP_SEP = 6`.

Write `N = sample_count`, `x[0..N-1]` for the raw samples, and
`W = 2 * INTEGRATION_HALF_WIDTH + 1 = 17` for the nominal gate width.

## 1. Two-pass robust baseline

The baseline is estimated from the pre-trigger region `x[0 .. PRE_TRIGGER-1]` only.
Post-trigger samples never enter the baseline, no matter how quiet they look.

**Pass 1 — provisional location and scale.**

```
m1    = median(x[0 .. PRE_TRIGGER-1])
mad1  = median(|x[i] - m1|)  over the same window
sigma1 = MAD_SCALE * mad1
```

The median of an even-length window is the arithmetic mean of the two central order
statistics.

**Pass 2 — outlier rejection and final estimate.**

Retain the samples satisfying `|x[i] - m1| <= OUTLIER_K * sigma1`. Call the retained
set `S` and `n_base = |S|`.

```
baseline = median(S)
mad2     = median(|x[i] - baseline|)  over S
sigma    = MAD_SCALE * mad2
```

**Fallbacks.** Two degenerate cases are resolved before the cut is applied:

- If `sigma1 == 0` — a perfectly flat pre-trigger window — the cut would keep only the
  samples exactly equal to `m1`. Instead retain the entire pre-trigger window:
  `S = x[0 .. PRE_TRIGGER-1]`, `n_base = PRE_TRIGGER`.
- If the cut retains fewer than `MIN_BASELINE_SAMPLES` samples, the pre-trigger region
  is too disturbed for the cut to be meaningful. Discard the cut and fall back to the
  full pre-trigger window: `baseline = m1`, `sigma = sigma1`, `n_base = PRE_TRIGGER`.

**Noise variance.** The per-sample noise variance is

```
noise_var = max(sigma^2, 1/12)
```

The floor is the variance of a uniformly distributed quantization error of one LSB and
keeps a noiseless synthetic trace from producing zero-variance weights.

**Baseline variance.** The baseline is a median of `n_base` samples, so its sampling
variance is the asymptotic Gaussian median variance

```
baseline_var = (pi / 2) * noise_var / n_base
```

This term is fully correlated across the samples of one frame, which is why it enters
the charge variance quadratically below.

## 2. Polarity and correction

The frame header carries `polarity` (`+1` or `-1`). The corrected trace is

```
c[i] = polarity * (x[i] - baseline)
```

so a physical pulse is a positive excursion in `c` for both polarities. Every later
step — peak search, integration, pile-up — works on `c`, never on raw samples.
Saturation is the only test that inspects raw samples.

Polarity is read from each frame. It is not inferred from the samples, and it is not
taken from the profile: the crate records it with the acquisition.

## 3. Peak location

For pulser frames (`kind = 1`), search the post-trigger region only:

```
peak = argmax over i in [PRE_TRIGGER, N-1] of c[i]
```

Ties resolve to the smallest index. The search runs to the last sample of the record;
it is not shortened to keep the gate inside the trace. A pulse whose maximum lands near
the end of the record therefore produces a clipped gate, which is handled by the
coverage test rather than by moving the peak.

For pedestal frames (`kind = 0`) there is no peak search. The pedestal gate is the
fixed window `[PRE_TRIGGER, PRE_TRIGGER + 2*INTEGRATION_HALF_WIDTH]`, i.e. the same
`W` samples the digitizer would have integrated had a pulse arrived on time. Because
`N >= 64` and `PRE_TRIGGER + 2*INTEGRATION_HALF_WIDTH = 48`, the pedestal gate is
always complete and a pedestal frame always has `coverage = 1`.

## 4. Gate integration

The nominal gate is `[peak - INTEGRATION_HALF_WIDTH, peak + INTEGRATION_HALF_WIDTH]`
inclusive. Clip it to the record:

```
lo = max(0, peak - INTEGRATION_HALF_WIDTH)
hi = min(N - 1, peak + INTEGRATION_HALF_WIDTH)
n_actual = hi - lo + 1
charge   = sum of c[i] for i in [lo, hi]
coverage = n_actual / W
```

Indices outside the record are not summed and are not padded with zeros. The sum is
not divided by `n_actual` and is not rescaled to compensate for clipping; `coverage`
records how much of the nominal gate survived, and the pedestal subtraction uses it
(`rolling_pedestal.md`).

**Charge variance.** The `n_actual` summed samples each carry independent noise, and
all of them share one baseline estimate:

```
charge_var = n_actual * noise_var + n_actual^2 * baseline_var
```

The linear term is the independent sample noise; the quadratic term is the common
baseline error propagated through the sum. Dropping the quadratic term understates the
uncertainty of wide gates and biases the fit weights.

## 5. Frame-quality tests

Tests are applied in the order below. The first test a frame fails determines its
rejection counter; a frame is never counted twice.

1. **Saturation.** The frame is saturated when any raw sample satisfies
   `x[i] >= rail_high` or `x[i] <= rail_low` for the shard's `adc_bits`
   (`container.md`). Both rails are checked on every frame regardless of polarity.
   Saturated frames — pedestal or pulser — are rejected and increment
   `frames_rejected_saturation`. A saturated pedestal frame does not enter the rolling
   pedestal population.
2. **Coverage.** A pulser frame with `coverage < MIN_COVERAGE` is rejected and
   increments `frames_rejected_coverage`. With `W = 17` the test admits gates of at
   least 12 samples.
3. **Pile-up.** Let `peak_amp = c[peak]`. Search for a secondary extremum

   ```
   sec = max of c[i] over i in [PRE_TRIGGER, N-1] with |i - peak| > PILEUP_SEP
   ```

   If that index set is empty, there is no pile-up. Otherwise the frame is rejected as
   piled up when `sec >= PILEUP_FRAC * peak_amp` and `sec > 0`, and it increments
   `frames_rejected_pileup`. A non-positive `peak_amp` cannot pass this test with a
   positive `sec`, so such frames are rejected as well.

   Pile-up is tested on pulser frames only. A pedestal trace carries no pulse, so its
   two largest noise excursions would compare as pile-up on nearly every frame.

Frames that pass every applicable test are *reduced*. Reduced pedestal frames feed the
rolling pedestal population (`rolling_pedestal.md`); reduced pulser frames become
candidate fit observations, subject to the pedestal-availability and noise rules in
that document.

## 6. Metamorphic properties

These follow from the definitions above and are checked independently:

- **Uniform ADC shift.** Adding the same constant to every sample of a frame, without
  reaching a rail, leaves `charge`, `charge_var`, and `coverage` unchanged; only
  `baseline` moves by the constant.
- **Polarity flip.** Negating every corrected excursion and flipping the header
  `polarity` leaves `charge`, `coverage`, `peak`, and all frame-quality outcomes
  unchanged.
- **Record extension.** Appending baseline-level samples after a fully covered gate
  changes nothing; appending them after a clipped gate raises `coverage` and can turn a
  rejected frame into a reduced one.
