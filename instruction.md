# Digitized PMT charge response: campaign reduction disagrees with hand audit

At the calorimeter facility, operators run an offline HV-pulser workflow that must
produce a per-lane gain report and replay ledger from PMW2 photomultiplier waveform
shards. The workspace lives at /app/environment. Campaign reductions exit successfully,
yet a separate numerical audit of the same digitizer records disagrees with the published
artifacts, and the mismatch pattern changes from lane to lane.

Observed failures:

- Digitizer shards that the crate produced can be rejected while malformed containers
  are sometimes accepted, so published gains occasionally incorporate bytes that are
  not ADC samples.
- Changing only the order of shard names in the runbook changes the published gains,
  and when two crates record the same acquisition the survivor depends on list order
  rather than the documented shard priority.
- Manual gate sums disagree with published charges when the pulse peak sits near the
  end of the trace or when a second pulse sits on the trailing shoulder.
- One contaminated pre-trigger sample moves the baseline, and rail hits are treated
  differently at the positive rail than at the negative rail.
- On hv-neg-edge-d the fitted gains come back near zero or negative even though the
  crate log shows clean inverted pulses.
- Time-varying pedestal populations are treated as static: mid-scan pedestal changes
  do not reweight later pulsers, noisy intervals never clear, and some pulser rows
  appear to have been corrected with later pedestal frames.
- Uncertainties collapse when many pulsers share one pedestal epoch, and the residual
  quadratic form is not a chi-square under the stated covariance.
- When every pulser on a lane shares one timestamp so drift is unidentified, the fit
  still returns a confident gain and drift pair.
- Reference-normalized tables disagree with raw gain ratios, the reference lane is not
  exactly unity, and the quoted ratio uncertainties omit the shared pulser source.
- Provenance counters do not reconcile with frames read, and known rejection classes
  stay at zero.
- Identical offline replays produce different digests, and one interrupted publish left
  a new report paired with a stale ledger.

## Required capability

Implement the complete offline PMW2 gain-reduction capability under /app/environment so
the ordinary hvreduce calibrate path regenerates tables that match the written scientific
contract. Driver-only wrappers are not enough; the waveform, pedestal, GLS, and
normalization modules must themselves obey the docs.

## Operator entry points

python3 /app/environment/hvreduce.py calibrate hv-raw-a
python3 /app/environment/hvreduce.py calibrate hv-norm-b
python3 /app/environment/hvreduce.py calibrate hv-interleave-c
python3 /app/environment/hvreduce.py calibrate hv-neg-edge-d

A successful calibrate writes /app/output/hv_gain_table.json and
/app/state/hv_replay_ledger.json and exits 0. A contract violation must raise
ValueError, print the message on stderr, exit 1, and leave neither artifact nor a
temporary file behind.

## Specification map

Shard lists, optional reference lanes, and shared-source covariance live in
/app/environment/runbook/campaign.toml.

The scientific and schema contracts live under /app/docs/:
/app/docs/overview.md,
/app/docs/container.md,
/app/docs/waveform.md,
/app/docs/rolling_pedestal.md,
/app/docs/gls_calibration.md,
/app/docs/lane_scale.md,
/app/docs/artifacts.md, and
/app/docs/profiles.md.

## Hard limits

- Remain air-gapped. The reduction must not use the network, wall clock, or a random source.
- Do not edit, regenerate, rename, or delete shards under /app/environment/fixtures/,
  and do not retune bundled runbook entries.
- Do not edit the verification suite or invent fixtures or campaigns to satisfy it.
- Do not hand-author JSON products, embed lookup tables, or key behaviour on campaign
  names, lane ids, basenames, or run ids.
- Verification clears /app/output and /app/state and may seed stale files before a run.
  Both products must be rebuilt from the shards either way.
- Verification also injects valid PMW2 shards and temporary campaigns absent from the
  bundled set, so correctness must follow the docs rather than memorized fixtures.
- Holdout campaigns under /opt/verifier-fixtures (including TB3_LINEAR, TB3_NEGATIVE_POLARITY, and TB3_PEDESTAL_RECOVERY) follow the same contracts.
- The independent verifier reduction module is named ref_eval; it is not part of the
  /app/environment workspace and must not be imported by the reduction under test.
