# Output contract

## Invocation, ordering, and numerical decisions

Implement `/app/estimate.R`. The harness calls `/app/run.sh [data-directory]
[output-path]`; the defaults are `/app/data` and
`/app/outputs/results.csv`. Read fields by header. Physical row and column
order are irrelevant. Sort opaque strings by UTF-8 byte order under the C
locale and clusters numerically.

Define `D(x)=floor(10000000*x+0.5)`. Every comparison described as a numerical
decision compares `D(x)`, not raw doubles. Remaining stated ordering keys are
applied only after equality of the preceding decision codes.

The six relations are:

- `cases.csv`:
  `case_id,edge_probability_floor,safety_floor,ess_floor,safety_weight,robustness_scale,cv_penalty,cycle_instability_penalty,max_deleted_clusters`
  where `max_deleted_clusters` is a positive integer
- `states.csv`: `case_id,state_id`
- `cluster_roster.csv`:
  `case_id,cluster,exposure_weight,stress_score`; exposure weights are positive
- `priors.csv`:
  `case_id,from_state,to_state,prior_mass,prior_value`; every ordered state pair
  occurs once and prior mass is positive
- `regularizers.csv`:
  `case_id,candidate_id,candidate_rank,lambda,covariance_ridge,support_z`;
  candidate IDs are unique, ranks are distinct positive integers, and the
  three numeric candidate parameters are finite and nonnegative
- `records.csv`:
  `case_id,policy_id,cluster,event_id,state_id,next_state,reward,cost,target_prob,behavior_prob,noise_a,source_id`;
  probabilities are positive. Event, noise, and source fields do not enter any
  calculation.

Each case has the same nonempty policy set in every roster cluster.

The evaluator must exit nonzero without writing an output when a required
relation is missing; a case repeats a roster cluster, candidate ID, or
candidate rank; an
ordered prior cell is missing or nonpositive; a record refers to a state or
cluster outside its case; a target or behavior probability is nonpositive or
nonfinite; or the policy-by-cluster record grid is incomplete.

## Candidate-specific cluster models

For a record define `w=target_prob/behavior_prob` and `u=reward-cost`. For
candidate `q`, policy `p`, cluster `c`, and edge `(s,t)`, let

`M=sum(w on matching records)`

`A=M+lambda[q]*prior_mass[s,t]`

`P[q,p,c,s,t]=A/sum_v A[s,v]`

`V[q,p,c,s,t]=(sum(w*u on matching records)+lambda[q]*
prior_mass[s,t]*prior_value[s,t])/max(A,1e-300)`.

For retained clusters `C`, normalize roster exposures as
`a_c=exposure_weight[c]/sum_C exposure_weight`. The pooled transition is
`Pbar[s,t]=sum_C a_c*P[q,p,c,s,t]`. Its lower support value is

`L[s,t]=Pbar[s,t]-support_z[q]*
sqrt(sum_C a_c*(P[q,p,c,s,t]-Pbar[s,t])^2)`.

An edge is present exactly when `D(L[s,t]) >=
D(edge_probability_floor)`.

## Cycle metric for one candidate and policy

Enumerate every directed simple cycle of the support graph, including
self-loops. A simple cycle repeats no state except its closing state. Rotate
its state sequence so the smallest state ID is first, append that state, and
join IDs with `>`.

For cycle `g` and cluster `c`, `m_c(g)` is the arithmetic mean of
`V[q,p,c,s,t]` over its edges. Define

`center(g)=sum_C a_c*m_c(g)`

`covariance(g)=sqrt(sum_C a_c*(m_c(g)-center(g))^2+
covariance_ridge[q]/length(g))`

`safety(g)=center(g)-robustness_scale*covariance(g)`.

The critical cycle minimizes `D(safety(g))`, then cycle code.
`minimum_cycle_mean`, `critical_cycle`, `critical_cycle_length`, and
`cycle_covariance_penalty` are its safety, code, length, and covariance.

For each critical-cycle edge, pool matching raw weights over retained
clusters and compute `edge_ess=sum(w)^2/sum(w^2)`, or zero when the
denominator is zero. `effective_sample_size` is the harmonic mean of these
edge ESS values, or zero if any is zero. `minimum_edge_support` is the
smallest `L` on the critical cycle. `support_edge_count` counts all present
ordered edges.

For policy and cluster,
`R_c=sum(w*u)/sum(w)` over every policy record in that cluster. Let

`R=sum_C a_c*R_c`

`lower_sd=sqrt(sum_C a_c*max(R-R_c,0)^2)`

`robust_policy_return=R-robustness_scale*lower_sd`

`policy_score=robust_policy_return+safety_weight*minimum_cycle_mean`.

## Global candidate validation

For each candidate, policy, and held-out retained cluster `h`, train on
`C\{h}`. If any resulting training support graph has no directed simple
cycle, that candidate's `cv_loss` is `1000000000+candidate_rank`.

Otherwise compute the held-cluster importance-weighted transition loss

`nll=-sum_h w*log(max(Pbar_train[state,next_state],1e-300))/sum_h w`.

For every ordered edge, compare the training lower-support decision with
`D(P[q,p,h,s,t]) >= D(edge_probability_floor)`. `support_error` is the
fraction of mismatches.

Use the training critical cycle. Let `held_cycle` be the arithmetic mean of
the held cluster's `V` values on that cycle and `train_cycle` its training
`center`. The contribution is

`z=nll+cv_penalty*support_error+
cycle_instability_penalty*(held_cycle-train_cycle)^2`.

Weight this contribution by
`b_h=exposure_weight[h]*(1+0.2*abs(stress_score[h]))`, separately for every
policy-holdout pair. With `zbar=sum(b*z)/sum(b)`, define

`cv_loss=zbar+0.15*sqrt(sum(b*(z-zbar)^2)/sum(b))`.

Select the candidate minimizing `D(cv_loss)`, then candidate rank, then
candidate ID. The same one selected candidate evaluates every policy.

## Policy choice

A policy is feasible exactly when
`D(minimum_cycle_mean) >= D(safety_floor)` and
`D(effective_sample_size) >= D(ess_floor)`. `feasible_count` counts feasible
policies. Select from feasible policies when this set is nonempty, otherwise
from all policies. Order by decreasing `D(policy_score)`, decreasing
`D(minimum_cycle_mean)`, decreasing `D(effective_sample_size)`, then
increasing policy ID.

## Complete deletion refits

First fit all clusters. Enumerate deletion sets of sizes one through
`min(max_deleted_clusters,cluster_count-4)`, ordered by size and then
lexicographically over numerically sorted cluster IDs. A deleted cluster's
zero-based full-data rank contributes bit `2^rank`; a scenario code is the
sum of its bits.

For every scenario, repeat candidate validation and every policy calculation
using only retained clusters. Join
`scenario_code:candidate_id:policy_id:critical_cycle` entries with `|` to
form `deletion_code`. `deletion_change_count` counts identities differing
from the full selected candidate, policy, or critical cycle.

`worst_deletion_safety` is the scenario's smallest selected safety by
numerical decision; its tie uses smaller scenario code.
`worst_deletion_scenario_code` is that code.
`maximum_deletion_covariance` is the largest raw selected cycle covariance.

For each scenario define

`T=11*candidate_rank+13*D(cv_loss)+17*D(policy_score)+
19*D(robust_policy_return)+23*D(minimum_cycle_mean)+
29*D(effective_sample_size)+31*support_edge_count+
37*D(minimum_edge_support)+41*D(cycle_covariance_penalty)`.

`stability_checksum` is `sum(scenario_code*T) mod 2147483647`, using a
nonnegative remainder.

## Output and audit signature

Write one unquoted row per case, sorted by case ID, with exactly:

`case_id,selected_candidate,selected_policy,feasible_count,policy_score,robust_policy_return,minimum_cycle_mean,critical_cycle,critical_cycle_length,cycle_covariance_penalty,effective_sample_size,support_edge_count,minimum_edge_support,cv_loss,deletion_code,deletion_change_count,worst_deletion_safety,worst_deletion_scenario_code,maximum_deletion_covariance,stability_checksum,audit_signature`

Numeric fields must be finite, emitted at full double precision, and accurate
within absolute error `3e-8`.

The signature payload joins with `|`, in this order: case ID, selected
candidate, selected policy, critical cycle, deletion code, `D(policy_score)`,
`D(robust_policy_return)`, `D(minimum_cycle_mean)`,
`D(cycle_covariance_penalty)`, `D(effective_sample_size)`,
`support_edge_count`, `D(minimum_edge_support)`, `D(cv_loss)`,
deletion change count, worst scenario code, and stability checksum.

Hash the payload's UTF-8 bytes with 32-bit FNV-1a: start at `2166136261`, XOR
each byte, multiply by `16777619`, and keep the low 32 bits. Render exactly
eight lowercase hexadecimal digits.
