# Output contract

## Invocation and numerical decisions

Run the evaluator with `Rscript /app/estimate.R DATA_DIR OUTPUT.csv`.
Defaults are `/app/data` and `/app/outputs/results.csv`. Use bytewise
lexicographic ordering for identifiers and numeric ordering for clusters.
Write cases in sorted `case_id` order.

Every comparison explicitly written as `D(x)` uses
`D(x)=floor(10000000*x+0.5)`. Other calculations use unrounded double
precision. All population variances below use the stated normalized weights.
Use `D` only where the contract explicitly invokes it for a comparison,
checksum, or signature. Write every floating-point output field as its raw,
unrounded double-precision value; never serialize `D(x)` in those columns.

## Relations and domain

Read these CSV relations by header name; extra columns and row/header order do
not matter.

- `cases.csv`:
  `case_id,edge_probability_floor,safety_floor,ess_floor,safety_weight,robustness_scale,cv_penalty,cycle_instability_penalty,prediction_penalty,calibration_ceiling,max_deleted_clusters`
- `states.csv`: `case_id,state_id`
- `cluster_roster.csv`: `case_id,cluster,exposure_weight,stress_score`
- `priors.csv`:
  `case_id,from_state,to_state,prior_mass,prior_value`
- `regularizers.csv`:
  `case_id,candidate_id,candidate_rank,lambda,covariance_ridge,support_z,response_ridge,calibration_z`
- `records.csv`:
  `case_id,policy_id,cluster,event_id,state_id,next_state,reward,cost,target_prob,behavior_prob,noise_a,source_id`

Each case has at least one state and candidate, at least five clusters, a
complete positive-mass directed prior grid, and the same nonempty policy set
in every cluster. Case/candidate parameters, exposures, stresses, priors,
utilities, probabilities, and `noise_a` are finite. Exposures, prior masses,
probabilities, `response_ridge`, and `max_deleted_clusters` are positive.
`lambda`, `covariance_ridge`, `support_z`, and `calibration_z` are
nonnegative. Candidate IDs and positive ranks are unique within a case.
Reject any bundle that violates any condition in this paragraph, including a
non-positive response ridge, a negative calibration value, or a non-finite
numeric input. Also reject invalid foreign keys, duplicate
case/state/cluster/prior/candidate/event keys, and incomplete required grids.
On rejection, exit nonzero and do not create the output file.

## Transition and support model

For a record let `w=target_prob/behavior_prob` and `u=reward-cost`. For policy
`p`, cluster `c`, and edge `(s,t)`, define:

- `M=sum(w)`, `Y=sum(w*u)`, and `Q=sum(w^2)`;
- candidate-smoothed mass `A=M+lambda*prior_mass(s,t)`;
- cluster transition `P_c(s,t)=A/sum_v A(s,v)`.

For retained clusters `C`, normalize their roster exposures to `a_c`.
`Pbar=sum_c a_c*P_c`. For each edge let
`L=mean_a(P_c)-support_z*sqrt(mean_a((P_c-mean_a(P_c))^2))`.
The support graph contains `(s,t)` exactly when
`D(L(s,t)) >= D(edge_probability_floor)`.

## Cross-fitted response model

State ranks are zero based in sorted state order. With
`d=max(number_of_states-1,1)`, define `x_s=2*rank(s)/d-1` and similarly
`x_t`. For a positive-mass cluster edge let
`z=sum(w*noise_a/1000)/M` and `z2=sum(w*(noise_a/1000)^2)/M`.
Its feature row is

`[1,x_s,x_t,x_s*x_t,1(s=t),prior_value,stress,stress^2,z,z2,stress*z]`.

For candidate `q`, policy `p`, and training clusters `T`, fit weighted ridge
regression to edge targets `Y/M`. Edge fit weights are `M/(1+M)`.
Minimize weighted squared error plus `response_ridge` times the squared
non-intercept coefficients; the intercept is unpenalized.

To predict held cluster `h`, evaluate this fit on every edge. If its raw edge
value is `r=Y/M`, let
`precision=M/(M+response_ridge*prior_mass)` and
`v=prediction+precision*(r-prediction)`. For a missing empirical edge use
`r=prediction`, so `v=prediction`.

The held RMSE is the square root of the edge-fit-weighted mean squared
`r-prediction`. The held correction is the same weights' mean
`abs(v-r)`. The held fitted policy return averages, uniformly across source
states, `sum_t P_h(s,t)*v(s,t)`.

For every cluster in a retained set, fit on all other retained clusters and
hold that cluster out. Let `e_c`, `k_c`, and `R_c` be its RMSE, correction,
and fitted return. Define:

- `predictive_calibration=mean_a(e_c)+calibration_z*sd_a(e_c)`;
- `crossfit_correction=mean_a(k_c)`.

## Cycle safety and policy score

Enumerate every directed simple cycle in the support graph, including
self-loops. A cycle repeats no state except its closing state. Rotate it to
start at its smallest state and render the closed path with `>`.

For a cycle `g`, `m_c(g)` is the arithmetic mean of held predicted edge
values on the cycle. Let
`center=mean_a(m_c)` and
`covariance=sqrt(var_a(m_c)+covariance_ridge/length(g))`. Its safety is

`center-robustness_scale*(covariance+predictive_calibration/sqrt(length(g)))`.

The critical cycle minimizes `D(safety)`, then cycle code.
`minimum_cycle_mean`, `critical_cycle`, `critical_cycle_length`, and
`cycle_covariance_penalty` report its values.

For a critical-cycle edge, pool raw weights over retained clusters and set
`edge_ess=sum(w)^2/sum(w^2)`, or zero if the denominator is zero.
`effective_sample_size` is the harmonic mean across cycle edges, or zero when
any edge ESS is zero. `minimum_edge_support` is the smallest `L` on the cycle.
`support_edge_count` counts all supported edges.

Let `return_center=mean_a(R_c)` and
`downside=sqrt(mean_a(max(return_center-R_c,0)^2))`. Then

- `robust_policy_return=return_center-robustness_scale*downside-0.25*predictive_calibration`;
- `policy_score=robust_policy_return+safety_weight*minimum_cycle_mean-0.1*crossfit_correction`.

## Global candidate validation

For each candidate, policy, and held retained cluster `h`, train on all other
retained clusters. If that training graph has no cycle, the candidate
`cv_loss` is `1000000000+candidate_rank`.

Otherwise compute:

- importance-weighted held transition NLL under training `Pbar`;
- the fraction of all edges whose training support decision differs from the
  held cluster's smoothed-transition support decision;
- squared difference between the training critical-cycle center and the
  arithmetic mean of the externally held response predictions on that cycle;
- the externally held response RMSE.

For held retained cluster `h`, let `T` be all retained clusters except `h`.
Compute the training policy metric on `T` using the ordinary response-surface
procedure, including its inner leave-one-cluster-out fits within `T`. Its
selected critical cycle and cycle center are the training critical cycle and
training critical-cycle center. Separately fit one response model using all
clusters in `T`, evaluate the observations in `h`, and apply the documented
response adjustment to obtain the externally held predictions. The
instability term is the squared difference between the training cycle center
and the arithmetic mean of those adjusted held predictions along the training
critical cycle.

Their sum is
`NLL + cv_penalty*support_error + cycle_instability_penalty*instability +
prediction_penalty*RMSE`. Weight each contribution by
`exposure_weight*(1+0.2*abs(stress_score))`. Candidate `cv_loss` is the
weighted mean plus `0.15` times its weighted standard deviation.

Select the candidate minimizing `D(cv_loss)`, then candidate rank, then
candidate ID. One selected candidate evaluates every policy.

## Policy choice and deletion refits

A policy is feasible when
`D(minimum_cycle_mean)>=D(safety_floor)`,
`D(effective_sample_size)>=D(ess_floor)`, and
`D(predictive_calibration)<=D(calibration_ceiling)`.
Use feasible policies if any, otherwise all policies. Select by decreasing
`D(policy_score)`, decreasing `D(minimum_cycle_mean)`, decreasing
`D(effective_sample_size)`, increasing `D(predictive_calibration)`, then
policy ID. Report the number feasible before fallback.

First fit all clusters. Enumerate deletion sets of sizes one through
`min(max_deleted_clusters,cluster_count-4)`, ordered by size and then
lexicographically over numerically sorted cluster IDs. A scenario code is the
sum of `2^r`, where `r` is the deleted cluster's zero-based roster rank.
Completely repeat candidate validation and policy fitting on retained
clusters. Join
`scenario_code:candidate_id:policy_id:critical_cycle` with `|` as
`deletion_code`. Count identities different from the full fit.

`worst_deletion_safety` is the smallest selected safety by `D`, breaking ties
by scenario code. Report that code. The two deletion maxima are the largest
raw selected covariance and calibration.

For each scenario define

`T=11*candidate_rank+13*D(cv_loss)+17*D(policy_score)+19*D(robust_policy_return)+23*D(minimum_cycle_mean)+29*D(effective_sample_size)+31*support_edge_count+37*D(minimum_edge_support)+41*D(cycle_covariance_penalty)+43*D(predictive_calibration)+47*D(crossfit_correction)`.

`stability_checksum=sum(scenario_code*T) mod 2147483647`.

## Output and signature

Write exactly these columns:

`case_id,selected_candidate,selected_policy,feasible_count,policy_score,robust_policy_return,minimum_cycle_mean,critical_cycle,critical_cycle_length,cycle_covariance_penalty,predictive_calibration,crossfit_correction,effective_sample_size,support_edge_count,minimum_edge_support,cv_loss,deletion_code,deletion_change_count,worst_deletion_safety,worst_deletion_scenario_code,maximum_deletion_covariance,maximum_deletion_calibration,stability_checksum,audit_signature`

Join with `|`: case ID, candidate, policy, critical cycle, deletion code,
`D(policy_score)`, `D(robust_policy_return)`, `D(minimum_cycle_mean)`,
`D(cycle_covariance_penalty)`, `D(predictive_calibration)`,
`D(crossfit_correction)`, `D(effective_sample_size)`, support count,
`D(minimum_edge_support)`, `D(cv_loss)`, deletion change count, worst scenario
code, `D(maximum_deletion_calibration)`, and checksum. Encode integers as
ordinary decimal text. `audit_signature` is lowercase eight-digit FNV-1a
32-bit hexadecimal of the UTF-8 payload, with offset basis `2166136261` and
prime `16777619`.
