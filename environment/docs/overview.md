Photomultiplier ADC·sample charge response under HV-pulser illumination.

# Calorimeter PMT offline calibration — overview

The test-stand workspace under `/app/environment` reduces PMW2 waveform acquisition
shards from calorimeter photomultiplier readout lanes into a reproducible per-lane
gain table. A nightly replay must be bit-identical to any later replay of the same
inputs, and independent reductions of the same shards must agree with the published
numbers.

This document is the entry point. Every externally checked contract is written down
in one of the documents listed below; nothing in the pipeline is allowed to depend on
behaviour that is not documented here.

| Document | Contract |
|---|---|
| `container.md` | PMW2 container layout, validation, decoder error policy, merge |
| `waveform.md` | Baseline estimation, polarity, charge integration, frame quality |
| `rolling_pedestal.md` | Rolling pedestal population, epochs, per-observation variance |
| `gls_calibration.md` | Generalized least squares gain/drift fit, statuses, diagnostics |
| `lane_scale.md` | Reference-lane normalization and delta-method uncertainty |
| `artifacts.md` | Artifact fields, deterministic JSON, digests, atomic writes |
| `profiles.md` | Profile declarations and the scenario each one exercises |

## Pipeline stages

The reduction is a strict pipeline. Each stage consumes the documented output of the
previous stage; no stage may look ahead.

1. **Decode.** Read every shard listed by the profile, validate the container, and
   materialize frames with their raw samples (`container.md`).
2. **Merge.** Deduplicate acquisition identities across shards using shard priority,
   then place the surviving frames into documented process order (`container.md`,
   section *Merge*).
3. **Reduce signals.** For each frame, estimate the baseline, apply polarity, locate
   the pulse, integrate the gate, and apply the frame-quality tests
   (`waveform.md`).
4. **Track pedestals.** Maintain a per-lane rolling pedestal population; each accepted
   pulser observation freezes the pedestal estimate and epoch that were current at its
   process time (`rolling_pedestal.md`).
5. **Fit.** Solve one generalized least squares fit per lane for intercept, gain, and
   drift under a covariance matrix that carries the shared-pedestal common-mode term
   (`gls_calibration.md`).
6. **Normalize.** On profiles that declare a reference lane, convert gains to a ratio
   against the reference and propagate the uncertainty with the delta method
   (`lane_scale.md`).
7. **Publish.** Round, encode documentedly, digest, and write both artifacts
   atomically (`artifacts.md`).

## Constants

These values are fixed by the calibration contract. They are defined once in the
shared acquisition constants module and must not be re-declared with different values
elsewhere.

| Constant | Value | Meaning |
|---|---|---|
| `SCHEMA_VERSION` | `2` | Version stamped into both artifacts |
| `FILE_HEADER_BYTES` | `24` | PMW2 file header size |
| `FRAME_HEADER_BYTES` | `28` | PMW2 frame header size |
| `PRE_TRIGGER` | `32` | Pre-trigger samples reserved for baseline estimation |
| `INTEGRATION_HALF_WIDTH` | `8` | Half-width of the charge gate, in samples |
| `GATE_WIDTH` | `17` | Nominal gate width, `2 * INTEGRATION_HALF_WIDTH + 1` |
| `MIN_COVERAGE` | `0.70` | Minimum fraction of the nominal gate that must be present |
| `OUTLIER_K` | `3.0` | Robust outlier cut, in units of sigma |
| `MAD_SCALE` | `1.4826` | MAD-to-sigma consistency factor for Gaussian noise |
| `MIN_BASELINE_SAMPLES` | `8` | Minimum retained pre-trigger samples after the outlier cut |
| `QUANTIZATION_VAR` | `1/12` | Variance floor of a uniform one-LSB quantization error |
| `MEDIAN_VARIANCE_FACTOR` | `pi/2` | Asymptotic variance of a median relative to a mean |
| `PILEUP_FRAC` | `0.35` | Secondary-to-primary amplitude ratio that flags pile-up |
| `PILEUP_SEP` | `6` | Sample separation outside which a secondary extremum counts |
| `PEDESTAL_K` | `8` | Rolling pedestal window length, in pedestal frames |
| `PEDESTAL_P` | `4` | Minimum pedestal frames required before a pulser is usable |
| `PEDESTAL_VAR_FLOOR` | `1.0` | Variance floor of the rolling pedestal population |
| `NOISE_SIGMA_LIMIT` | `12.0` | Pedestal-charge sigma above which observations are noisy |
| `MIN_OBS` | `6` | Minimum accepted observations for a fitted lane |
| `MIN_DISTINCT_LEVELS` | `3` | Minimum distinct pulser levels for a fitted lane |
| `COND_THRESHOLD` | `1e12` | Condition-number limit for the normal-equation matrix |
| `COMMON_MODE_SCALE` | `0.25` | Shared-pedestal covariance fraction |
| `PUBLICATION_DIGITS` | `9` | Decimal digits kept in published floats |

Charge is expressed in ADC counts summed over gate samples ("ADC·sample"). Time is
expressed in seconds, converted from the frame timestamp in nanoseconds.

## Command line

```bash
python3 /app/environment/hvreduce.py calibrate <profile>
python3 /app/environment/hvreduce.py calibrate <profile> --report <path> --state <path>
```

`<profile>` names a section of `/app/environment/runbook/campaign.toml`. The profile table
is read from disk on every invocation; profiles are never cached, precomputed, or
enumerated in source. Default artifact paths are `/app/output/hv_gain_table.json`
and `/app/state/hv_replay_ledger.json`.

Invoked with `-h` or `--help`, the tool prints usage to standard output and exits `0`.
Invoked with no arguments, an unknown subcommand, or `calibrate` without a profile
name, it prints usage and exits `1`.

## Failure policy

Any violation of a documented contract — malformed container, inconsistent shard set,
unknown profile, unusable reference lane — is reported by raising `ValueError`. The
CLI prints the message to standard error and exits with status `1`. A failed run
writes no artifact and leaves any pre-existing artifact untouched: there are no
partial products.

A successful run exits with status `0` and writes both artifacts.

## Global invariants

- **Order invariance.** Permuting the `shards` list of a profile changes nothing in
  either artifact, including both digests.
- **Replay determinism.** Re-running the same profile on the same inputs reproduces
  both artifacts byte for byte.
- **No look-ahead.** A pulser observation is reduced using only pedestal information
  that precedes it in documented process order.
- **No identity keying.** The reduction never keys behaviour on a profile name, lane
  id, shard basename, or run id. A profile it has never seen is served by the same
  code path as a bundled one.
- **Offline only.** The reduction reads the bundled shards and the profile table and
  nothing else. No network access, no clock reads, no random number sources.
- **Fixtures are read-only.** The bundled acquisition shards under
  `/app/environment/fixtures/` are inputs, never outputs.

## Verifier holdouts

Verification may inject temporary campaigns and refer to sealed markers under
`/opt/verifier-fixtures` such as `TB3_LINEAR`, `TB3_NEGATIVE_POLARITY`, and
`TB3_PEDESTAL_RECOVERY`. Exact sealed trees include
`/opt/verifier-fixtures/hv-campaign/TB3_LINEAR`,
`/opt/verifier-fixtures/hv-campaign/TB3_NEGATIVE_POLARITY`, and
`/opt/verifier-fixtures/hv-campaign/TB3_PEDESTAL_RECOVERY`. Those holdouts follow
the same contracts as the bundled profiles; they are not alternate reduction paths.

Host-side verifier scratch uses a `.verifier-run` directory when pytest is not
inside the container. Injected negative cases may briefly create names such as
`vfy_gone.pmw2` only under the verifier's temporary fixture overlay.

Bundled shard digests are recorded in `/app/environment/fixtures/SHA256SUMS.txt`.
