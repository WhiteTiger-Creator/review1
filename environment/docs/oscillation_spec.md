This specification defines a deterministic two-flavor neutrino propagation calculation through constant or linearly varying Earth matter density. The simulation is the Go module under `/app/environment`.
The module must remain internally consistent under `go -C /app/environment test ./...`.

Run it from `/app` with `go -C /app/environment run /app/environment/cmd/nuosc [--config CONFIG] [--propagation PROPAGATION] [--continuation CONTINUATION] [--reproducibility REPRODUCIBILITY] [--resume CONTINUATION] [--stop-after N | --stop-after-steps N]`.

The default paths are `/app/fixtures/earth_mantle_profile.json`, `/app/output/propagation.json`, `/app/output/continuation.json`, and `/app/output/reproducibility.json`. Positional arguments are invalid. `--stop-after N` is the total number of fully completed physical layers. `--stop-after-steps N` is the total number of completed numerical substeps. The stop flags are mutually exclusive. A requested boundary must not precede a resumed boundary or exceed the configured trajectory.

## Physical profile

Configuration JSON is decoded strictly. Unknown members, a second JSON value, and trailing non-whitespace bytes are invalid. Every numeric input described below must be finite.

Both schema versions contain `schema_version`, `mixing_angle_rad`, `delta_m2_ev2`, `energies_gev`, and `layers`. The mixing angle is strictly between zero and pi divided by two. `delta_m2_ev2` is positive. The energy grid is non-empty, positive, unique, and evaluated in ascending numeric order. Layer length is non-negative, density is non-negative, and `electron_fraction` is from zero through one. `config_sha256` is lowercase SHA-256 over the exact configuration bytes, including whitespace and the final newline.

Schema 1 is the constant-density form. It must not contain `max_phase_step_rad`. Each layer contains exactly `length_km`, `density_g_cm3`, and `electron_fraction`, and uses one numerical substep.

Schema 2 contains a positive `max_phase_step_rad` no greater than pi. Each layer contains exactly `length_km`, `density_start_g_cm3`, `density_end_g_cm3`, and `electron_fraction`. Density varies linearly between the two endpoints.

## Flavor evolution

For energy `E`, layer length `L`, density `rho`, electron fraction `Ye`, mixing angle `theta`, and mass-squared difference `dm2`, define the following quantities. Both primed amplitudes use the old electron and muon amplitudes.

```text
s = sin(2 theta); c = cos(2 theta); a = 7.56e-5 * rho * Ye * E / dm2; d = hypot(s, c - a); phase_magnitude = abs(1.267 * dm2 * L * d / E); count = max(1, ceil(max_endpoint_phase / max_phase_step_rad)); rho_mid = density_start_g_cm3 + (density_end_g_cm3 - density_start_g_cm3) * (j + 0.5) / count; substep_length = L / count; phi = 1.267 * dm2 * substep_length * d / E; nx = s / d; nz = (a - c) / d; electron' = (cos(phi) - i*nz*sin(phi))*electron + (-i*nx*sin(phi))*muon; muon' = (-i*nx*sin(phi))*electron + (cos(phi) + i*nz*sin(phi))*muon
```

For a non-zero schema 2 layer, `max_endpoint_phase` is the largest `phase_magnitude` found by evaluating both density endpoints for every configured energy. A zero-length layer has one no-op substep. Schema 1 always has one substep per layer.

Substeps are zero-indexed. Substep `j` has length `L / count` and uses the midpoint density above. All substeps are flattened in physical-layer order. `global_step` is the zero-based index in that flattened trajectory. A boundary stores the next physical layer, the next substep in that layer, and the number of completed global steps. At the terminal boundary, `next_layer` equals the layer count and `next_substep` is zero.

Every energy starts as a pure electron flavor with electron amplitude `(1, 0)` and muon amplitude `(0, 0)`. Each emitted probability norm error must be at most `0.000000000001`.

## Scientific fingerprints

Amplitude rows are ordered by `energy_gev`. Every float in a fingerprint uses Go `strconv.FormatFloat` with format `g`, precision 17, and bit size 64. Positive and negative zero serialize as `0`.

The fingerprint byte templates are exact: the state input is `boundary=<next_layer>:<next_substep>:<completed_steps>\n` followed by one `<energy>|<electron.real>|<electron.imag>|<muon.real>|<muon.imag>\n` line per ascending energy; the fresh trajectory-chain seed is `trace-v1\nconfig=<config_sha256>\n`; and after global step `k`, the next chain input is `prev=<previous_chain_sha256>\nstep=<k>\nstate=<state_sha256_after_step>\n`. All fingerprints are lowercase SHA-256 over UTF-8 bytes.

## Continuation state

A continuation state uses schema version 2 and contains exactly `schema_version`, `config_sha256`, `next_layer`, `next_substep`, `completed_steps`, `amplitudes`, `state_sha256`, and `trace_chain_sha256`.

Each amplitude contains `energy_gev`, `electron`, and `muon`, with each complex amplitude represented as a two-number real-imaginary pair. Reject a continuation state with the wrong schema, configuration identity, boundary, ascending energy set, finite-state condition, probability norm, state fingerprint, trajectory-chain format, or history. History validation repeats the public physical evolution from the fresh state to the recorded boundary. The repeated amplitudes must agree within `2e-12`, and the repeated trajectory chain must match exactly.

## Propagation result

`propagation.json` uses schema version 2 and contains exactly `schema_version`, `config_sha256`, `start_layer`, `start_substep`, `start_completed_steps`, `end_layer`, `end_substep`, `completed_steps`, `completed_layers`, `final_state_sha256`, `final_trace_chain_sha256`, `energies`, and `trace`.

`completed_layers` equals `end_layer`. Energy rows are ascending and contain `energy_gev`, `electron`, `muon`, `p_e`, `p_mu`, and `norm_error`.

The trace contains only substeps evaluated by that invocation. Rows are ordered by `global_step` and contain exactly `global_step`, `layer_index`, `substep_index`, `substep_count`, `midpoint_density_g_cm3`, `max_norm_error`, `state_sha256`, and `chain_sha256`.

## Reproducibility record

`reproducibility.json` uses schema version 1 and contains exactly `schema_version`, `config_sha256`, `mode`, `start_layer`, `start_substep`, `start_completed_steps`, `end_layer`, `end_substep`, `completed_steps`, `propagation_sha256`, `continuation_sha256`, `final_state_sha256`, and `final_trace_chain_sha256`.

`mode` is `fresh` or `resume`. The propagation and continuation hashes cover the exact bytes of those files. The final state and trajectory-chain values agree across all three scientific results.

## Result preservation and repeatability

All three files are UTF-8 JSON with two-space indentation and exactly one final newline. Parent directories are created when needed. The simulation completes profile loading, continuation validation, propagation, serialization, and temporary staging before replacing prior results.

The three files are one scientific result set. If a later replacement fails, every earlier file is restored byte for byte. A target that did not previously exist remains absent, an existing non-file target is not removed, and no sibling temporary or backup file remains.

A terminal continuation is valid. It emits an empty trace with identical start and end boundaries. Repeating the same terminal continuation command produces byte-identical propagation, continuation, and reproducibility files.
