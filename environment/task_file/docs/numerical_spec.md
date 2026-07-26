# Parallel Boys localization contract

The input is a JSON object with exactly `task` and `cases`. `task` is the string `boys-localization-sweep`; `cases` is a nonempty array whose case IDs are unique. JSON object member names must be unique. Every case has exactly these fields:

- `id`: a nonempty string, preserved in the output.
- `dipoles`: exactly three real symmetric `n` by `n` matrices. They are the Cartesian dipole matrices in the current orthonormal orbital basis, in the input's coherent length unit. Symmetric entries must be numerically equal as parsed. `n` is from 2 through 20, and every entry is a finite JSON number with absolute value at most `1000`.
- `frozen`: exactly `n` booleans. A pair containing a frozen orbital is unavailable; frozen orbitals otherwise remain in every matrix and output.
- `max_sweeps`: an integer from 1 through 20. Every sweep is performed, including empty later sweeps.
- `max_pairs_per_sweep`: a positive integer no greater than `floor(n/2)`.
- `work_budget`: a positive integer no greater than `2 * max_pairs_per_sweep`.
- `angle_cap_rad`: a finite number in `(0, pi/4]`, in radians.
- `min_gain`: a finite number in `[0, 1e9]`.
- `gain_quantum`: a finite number in `[1e-6, 1e9]`.
- `convergence_atol`: a finite number in `[0, 1e9]`.
- `convergence_rtol`: a finite number in `[0, 1e6]`.
- `frontier_size`: an integer from 1 through 5. This many first-ranked distinct complete plans must be retained for the per-sweep optimality audit, or every distinct plan when fewer exist.

Strings are never accepted in place of numbers, booleans, or integers. Unknown or missing fields, null arrays, ragged or nonsquare matrices, non-finite or out-of-range values, asymmetric matrices, duplicate IDs, duplicate object names, and an empty `cases` array are invalid.

## Rotation proposals

At the start of each sweep, use the three current dipole matrices `D[t]`, with `t=0,1,2`. For each available pair `i < j`, form three-component vectors

`x[t] = (D[t][i][i] - D[t][j][j]) / 2` and `y[t] = D[t][i][j]`,

then `a = sum_t x[t]^2`, `b = sum_t y[t]^2`, and `c = sum_t x[t]*y[t]`. If `a == b` and `c == 0` as floating-point values, its optimal angle is zero. Otherwise set

`theta_opt = 0.25 * atan2(2*c, a-b)`.

Canonicalize an angle equal to the upper endpoint by subtracting `pi/2`, so `theta_opt` is in the half-open interval `[-pi/4, pi/4)`. This is a per-pair calculation from the state at the start of the current sweep.

If `abs(theta_opt) <= angle_cap_rad`, the pair has one `direct` proposal with angle `theta_opt` and work cost 1. Otherwise it has two proposals: `capped`, with angle `copysign(angle_cap_rad, theta_opt)` and work cost 1, and `full`, with angle `theta_opt` and work cost 2.

For a proposal angle `theta`, let `ct = cos(theta)` and `st = sin(theta)`. For each Cartesian matrix define the proposed pair diagonals

`dii' = ct^2*D[i][i] + 2*ct*st*D[i][j] + st^2*D[j][j]`

`djj' = st^2*D[i][i] - 2*ct*st*D[i][j] + ct^2*D[j][j]`.

Its `predicted_gain` is the sum over the three matrices of `dii'^2 + djj'^2 - D[i][i]^2 - D[j][j]^2`. Its integer `gain_units` is `floor(predicted_gain / gain_quantum + 0.5)`. A proposal is eligible only when `predicted_gain > min_gain` and `gain_units >= 1`. Equality with `min_gain` is rejected. All proposal calculations use the unchanged start-of-sweep matrices.

## Complete sweep plan

A valid sweep plan contains at most one proposal for any orbital pair, no orbital index occurs in more than one selected proposal, its proposal count is at most `max_pairs_per_sweep`, and the sum of work costs is at most `work_budget`. The empty plan is valid.

Rank complete plans by these rules, in order:

1. greater sum of `gain_units`;
2. greater number of selected proposals;
3. smaller total work cost;
4. lexicographically smaller complete proposal sequence.

For the last rule, sort each sequence by ascending `i`, then `j`, then mode order `direct`, `capped`, `full`, and compare the resulting `(i,j,mode)` tuples. These rules compare complete plans, not the next locally best proposal.

Enumerate the distinct complete plans conceptually, rank all of them by the four rules, and retain the first `min(frontier_size, number_of_distinct_plans)` plans. The empty plan is one distinct plan. Two plans are distinct exactly when their canonical `(i,j,mode)` sequences differ. Apply only the first-ranked plan, but report the whole retained frontier as described below. An implementation must therefore preserve K-best alternatives at every exact dynamic-programming state; keeping only the locally best suffix is not sufficient.

The full supported domain includes dense 20-orbital cases with `max_pairs_per_sweep = 10`, where a sweep can contain up to 380 eligible proposals. Enumerating every proposal subset is not a compatible implementation strategy at those bounds. Every retained plan must be exact; greedy selection, a winner-only recurrence, beam search, and heuristic pruning that can discard a required frontier member are invalid.

Apply its rotations in that same canonical sequence. Each rotation uses the matrix state produced by earlier selected rotations. Selected pairs are disjoint, but this order is normative for floating-point evaluation. For each Cartesian matrix, copy the old matrix and set:

- the two diagonals to the `dii'` and `djj'` formulas above;
- `D'[i][j] = D'[j][i] = (ct^2-st^2)*D[i][j] + ct*st*(D[j][j]-D[i][i])`;
- for every `k` other than `i` and `j`, `D'[i][k] = D'[k][i] = ct*D[i][k] + st*D[j][k]` and `D'[j][k] = D'[k][j] = -st*D[i][k] + ct*D[j][k]`;
- every remaining entry is unchanged.

Maintain an `n` by `n` transform initialized to the identity. For the same rotation, update only its columns using old column values: `U'[k][i] = ct*U[k][i] + st*U[k][j]` and `U'[k][j] = -st*U[k][i] + ct*U[k][j]` for every row `k`.

The Boys objective is `sum_t sum_i D[t][i][i]^2`. `objective_trace` starts with the input objective and appends the recomputed objective after every sweep, so its length is `max_sweeps + 1`. Append the one-based sweep number to `accepted_sweeps` exactly when the selected plan's sum of start-of-sweep `predicted_gain` values is at most

`convergence_atol + convergence_rtol * abs(objective_after)`.

Acceptance is diagnostic and never short-circuits later sweeps. Empty plans have zero totals, leave the state unchanged, and are accepted whenever the nonnegative convergence bound permits it.

## Output and audit ordering

Output JSON has exactly one top-level field, `results`. Results remain in input case order. Each result has exactly:

- `id`: the input string.
- `transform`: the final `n` by `n` number matrix.
- `centroids`: an `n`-entry array; entry `i` is `[D[0][i][i], D[1][i][i], D[2][i][i]]` after the last sweep.
- `objective_trace`: the number array defined above.
- `accepted_sweeps`: an integer array in increasing order.
- `sweep_audit`: exactly `max_sweeps` records.
- `checksum`: the finite number defined below.

Each sweep record has exactly `sweep`, `rotations`, `plan_frontier`, `total_predicted_gain`, `total_gain_units`, `work_used`, and `objective_after`. `sweep` is one-based. Each rotation record has exactly `pair`, `mode`, `angle_rad`, `predicted_gain`, `gain_units`, and `work_cost`. Rotation records use the selected plan's canonical order.

`plan_frontier` contains the retained plans in best-to-worst order. Each frontier record has exactly `sequence`, `total_gain_units`, `proposal_count`, and `work_used`. `sequence` is the plan's canonical array of choice records, each of which has exactly `pair` and `mode`. The first frontier record describes `rotations`; all frontier totals are computed from the unchanged start-of-sweep proposals. If only the empty plan exists, the frontier contains its one record with `sequence: []` and zero totals. Empty `rotations`, `sequence`, and `accepted_sweeps` arrays are emitted as `[]`, never `null`.

The checksum uses final values and is

`sum_i sum_t (i+1)*(t+1)*centroids[i][t] + sum_r sum_c ((r+1)*(c+1)/n)*transform[r][c]`.

Do not round intermediate or output values. Every output number must be finite. Numerical grading uses `abs(actual-expected) <= 2e-10 + 2e-9*abs(expected)`; strings, integers, booleans, array lengths, field sets, plan choices, modes, indices, and ordering are exact.

The CLI accepts exactly the two documented positional arguments. Any argument, JSON, schema, dimension, symmetry, domain, or numerical failure must produce a nonzero exit. It must not create a new output or replace an existing output unless every case succeeds, and the output path must not refer to the input path.
