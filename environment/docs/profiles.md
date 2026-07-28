Bundled HV campaign scenarios for raw, normalized, interleaved, and negative-polarity runs.

# Calibration profiles

Profiles are declared in `/app/environment/runbook/campaign.toml`. Each profile is a TOML
table whose name is the argument passed to `hvreduce calibrate`.

| Key | Type | Required | Meaning |
|---|---|---|---|
| `shards` | string[] | yes | PMW2 shard basenames, resolved inside `/app/environment/fixtures/` |
| `reference_lane` | int | no | lane against which gains are normalized (`lane_scale.md`) |
| `shared_source_var` | float | no | pulser-source covariance `cov(g, r)`, default `0.0` |

The file is a TOML document and must be parsed as one — not scraped with pattern
matching, which reads the wrong section as soon as sections are reordered or a key is
commented out. Only tables are profiles: a top-level scalar such as a file-generation
marker is not a profile and must not be offered as one. Unknown keys inside a profile
table are ignored.

Loading failures abort the run with `ValueError`: a profile table that cannot be read, a
section that is absent (`unknown profile`), a missing or empty `shards` list
(`profile has no acquisition shards`), a `reference_lane` that is not an integer, or a
`shared_source_var` that is not a number.

Polarity is deliberately **not** a profile key. Every frame header carries its own
`polarity`, and that is the only authoritative source (`waveform.md`). A profile
can never override what the crate recorded.

The list order of `shards` is operator convenience only; merge priority is
`(shard_index, basename)` and `input_shards` is published lexicographically sorted, so
permuting the list changes nothing in either artifact.

The profile table is read from disk on every invocation. Profile names, shard lists,
reference lanes, and lane sets are never hardcoded, cached across runs, or special-cased
in the reduction code: the same code path must serve a profile it has never seen before.

## Bundled profiles

Each bundled profile isolates a different part of the contract. Their shard lists live
in `runbook/campaign.toml`; the descriptions below say what each one exercises, not what it
produces.

### `hv-raw-a` — raw

The nightly 12-bit acquisition, spread over three shards listed out of priority order.
No `reference_lane`, so gains are published in raw ADC·sample per level and `normalized`
is `false`. Its lanes cover the frame-quality and merge paths together: conflicting
duplicates of the same acquisition recorded into a second shard, byte-identical
duplicates, a repeated identity inside a single shard, pulsers that arrive before the
pedestal window is deep enough, pile-up contamination, pulses peaking late enough for
the gate to clip, acquisitions driven into a rail, and a lane driven at too few distinct
levels to determine three parameters. This is the profile where an error in the
baseline, charge, coverage, or pile-up rules shows up directly, undisguised by a ratio.

### `hv-norm-b` — normalized

The same nightly shards as `hv-raw-a`, listed in a different order, with a
`reference_lane` and a non-zero `shared_source_var`. Exercises reference-lane
normalization applied to the fully reduced dataset, the delta-method cross term, the
exact `1.0` published on the reference lane, and the requirement that the whole run
fails if the reference lane is not `ok`. Because it shares its inputs with `hv-raw-a`,
the two profiles together also pin down order invariance: every unnormalized column must
agree between them.

### `hv-interleave-c` — cross-shard, interleaved pedestals

A 14-bit run whose lanes are spread across three shards that overlap in acquisition
identity, some duplicates carrying identical payloads and some conflicting, so both
`frames_rejected_duplicate` and `frames_conflicting` are non-zero and retention depends
on shard priority rather than list order. Pedestal and pulser frames alternate in time on
the busy lanes, so a lane's rolling window changes mid-scan and successive observations
freeze different pedestal medians, different variances, and different epochs. One lane's
pedestal is unstable at the start of the run and recovers once enough clean pedestals
have rolled through; another never settles; another records pedestals and no pulsers at
all. This is the profile that separates a correct GLS covariance — with the common-mode
block for observations sharing an epoch — from an ordinary weighted fit, and that
punishes any look-ahead into pedestals recorded after the observation.

### `hv-neg-edge-d` — negative polarity

Every frame carries `polarity = -1`, so pulses are negative excursions from the baseline
and saturation occurs at the low rail. Exercises polarity handling end to end: baseline
estimation on an unchanged pre-trigger region, peak search on the corrected trace, the
low-rail saturation test, and clipped gates on late peaks — all producing positive gains
despite negative raw amplitudes. It also carries a lane whose acquisitions all share one
timestamp, so the drift regressor cannot be separated from the intercept and the lane
must be reported as `singular` rather than fitted. A pipeline that searches for maxima in
the raw samples finds pre-trigger noise here and reports near-zero or negative gains.

## Verifier-injected profiles

Verification may add temporary profile sections to `runbook/campaign.toml` and generate valid
PMW2 shards for them at test time, then remove both afterwards. These profiles are not
part of the bundled set and their names are not known to the reduction code. They are
constructed strictly to this contract, so the pipeline must handle them purely by reading
the profile table and decoding the shards.

## Fixtures are inputs

The acquisition shards under `/app/environment/fixtures/` are recorded data. They must
not be edited, regenerated, renamed, deleted, or "corrected" — including shards that
appear to hold saturated, clipped, piled-up, or duplicated frames. Those frames are the
measurement; rejecting them correctly is the work. The bundled entries of
`runbook/campaign.toml` are likewise fixed: shard lists, reference lanes, and
`shared_source_var` values are operator configuration, not tuning knobs for making a
reduction agree.
