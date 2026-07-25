# Output contract

## Invocation and input order

Implement `/app/estimate.R`. The harness calls `/app/run.sh [data-directory]
[output-path]`; defaults are `/app/data` and `/app/outputs/results.csv`. Read
fields by header. Physical row and column order are irrelevant. Sort opaque
string identifiers by UTF-8 byte order under the C locale, sort cluster
identifiers numerically, and regard numeric differences at most `1e-12` as
ties.

`cases.csv` contains
`case_id,edge_probability_floor,safety_floor,ess_floor,safety_weight,robustness_scale,cv_penalty,max_deleted_clusters`.

`states.csv` contains `case_id,state_id`.

`priors.csv` contains
`case_id,from_state,to_state,prior_mass,prior_value` for every ordered state
pair. Prior mass is positive.

`regularizers.csv` contains
`case_id,lambda_id,lambda_rank,lambda`; ranks are distinct positive integers.

`records.csv` contains
`case_id,policy_id,cluster,event_id,state_id,next_state,reward,cost,target_prob,behavior_prob,noise_a,source_id`.
Probabilities are positive. The event, noise, and source fields are
distractors.

## Cluster graph models

For each record let `w=target_prob/behavior_prob` and `u=reward-cost`. For
regularizer `lambda`, policy `p`, cluster `c`, and edge `(s,t)`, define

`mass = sum(w on matching records) + lambda*prior_mass[s,t]`

`P[p,c,s,t] = mass/sum_v mass[s,v]`

`V[p,c,s,t] = (sum(w*u on matching records) +
lambda*prior_mass[s,t]*prior_value[s,t])/max(mass,1e-300)`.

For a retained cluster set, the pooled transition probability of an edge is
the arithmetic mean of its cluster probabilities.

## Global regularizer selection

For every regularizer, policy, and held-out retained cluster, average the
cluster transition matrices over the other retained clusters. Evaluate the
held-out importance-weighted negative log likelihood:

`loss = -sum(w*log(max(P_train[state,next_state],1e-300)))/sum(w)`.

Combine every policy-holdout loss as

`cv_loss = mean(losses) + cv_penalty*population_sd(losses)`,

where population standard deviation divides by the number of values. Select
the smallest CV loss, resolving a tie by smaller `lambda_rank`.

## Policy safety functional

Using the selected regularizer, compute for every edge

`robust_edge_value = mean(V over retained clusters) -
robustness_scale*population_sd(V over retained clusters)`.

An edge is present exactly when its pooled transition probability is at least
`edge_probability_floor`. Consider every directed simple cycle in this graph,
including self-loops. A simple cycle repeats no state except its closing
state. Rotate its state sequence so its smallest state ID comes first, append
that state to close the cycle, and join IDs with `>`.

The policy `minimum_cycle_mean` is the smallest arithmetic mean of robust edge
values over all cycles. Resolve equal means by the smaller cycle code; this is
the `critical_cycle`.

For each critical-cycle edge, pool all matching raw importance weights across
retained clusters and compute `sum(w)^2/sum(w^2)`, using zero when no matching
record exists. `effective_sample_size` is the minimum edge ESS on the cycle.

For policy and cluster, compute
`cluster_return=sum(w*u)/sum(w)` across all its records. Define

`robust_policy_return = mean(cluster_return) -
robustness_scale*sqrt(mean(max(mean(cluster_return)-cluster_return,0)^2))`

`policy_score = robust_policy_return +
safety_weight*minimum_cycle_mean`.

A policy is feasible exactly when
`minimum_cycle_mean >= safety_floor` and
`effective_sample_size >= ess_floor`. `feasible_count` counts feasible
policies. Select from feasible policies when any exist, otherwise from all
policies, by decreasing policy score, decreasing minimum cycle mean,
decreasing ESS, then increasing policy ID.

## Deletion certificate

First select the global regularizer and policy on all clusters. Enumerate
cluster-deletion scenarios of sizes one through
`min(max_deleted_clusters, cluster_count-2)`, ordered by size and then
lexicographically over numerically sorted clusters. The zero-based full-data
rank of a deleted cluster contributes bit `2^rank`; sum the bits for the
scenario code.

For every scenario, repeat global regularizer selection and every policy
calculation from retained data. Join
`scenario_code:lambda_id:policy_id:critical_cycle` entries with `|` to form
`deletion_code`. `deletion_change_count` counts scenarios whose selected
lambda, policy, or critical cycle differs from the full identity.
`worst_deletion_safety` is the smallest deleted-fit minimum cycle mean;
`worst_deletion_scenario_code` is the first scenario attaining it under the
tie rule.

For one-based scenario rank `r`, supplied lambda rank, and one-based policy
rank among ascending policy IDs, define

`stability_checksum = sum(r*(policy_score + 2*robust_policy_return +
3*minimum_cycle_mean + 5*effective_sample_size + 7*cv_loss +
11*scenario_code + 13*lambda_rank + 17*policy_rank))`.

## Output and signature

Write one unquoted row per case sorted by `case_id`, with exactly:

`case_id,selected_lambda,selected_policy,feasible_count,policy_score,robust_policy_return,minimum_cycle_mean,critical_cycle,effective_sample_size,cv_loss,deletion_code,deletion_change_count,worst_deletion_safety,worst_deletion_scenario_code,stability_checksum,audit_signature`

Numeric fields must be finite and accurate within absolute error `3e-8`.

Scale by `1e8`, round ties-to-even, and render as base-10 integers these
full-fit values: policy score, robust return, cycle mean, ESS, CV loss, and
checksum. Join with `|`, in order: case ID, selected lambda, selected policy,
critical cycle, deletion code, the first five numeric codes, deletion change
count, worst scenario code, and checksum code. Starting at zero, process each
UTF-8 byte `b` at one-based position `k` as
`acc=(263*acc+b+k) mod 2147483647`. Render `acc` as eight lowercase
hexadecimal digits.
