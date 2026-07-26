args <- commandArgs(trailingOnly = TRUE)
data_dir <- if (length(args) >= 1L) args[[1L]] else "/app/data"
output_file <- if (length(args) >= 2L) {
  args[[2L]]
} else {
  "/app/outputs/results.csv"
}
Sys.setlocale("LC_COLLATE", "C")
options(digits = 17, scipen = 999)

read_relation <- function(name) {
  read.csv(
    file.path(data_dir, name),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

decision_code <- function(value) {
  floor(10000000 * value + 0.5)
}

cycle_code <- function(cycle, states) {
  paste(states[c(cycle, cycle[[1L]])], collapse = ">")
}

simple_cycles <- function(state_count, adjacency) {
  cycles <- list()
  for (start in seq_len(state_count)) {
    path <- start
    visited <- rep(FALSE, state_count)
    visited[[start]] <- TRUE
    visit <- function(current) {
      for (destination in adjacency[[current]]) {
        if (destination == start) {
          cycles[[length(cycles) + 1L]] <<- path
        } else if (!visited[[destination]] && destination > start) {
          visited[[destination]] <<- TRUE
          path <<- c(path, destination)
          visit(destination)
          path <<- path[-length(path)]
          visited[[destination]] <<- FALSE
        }
      }
    }
    visit(start)
  }
  cycles
}

fnv1a <- function(payload) {
  high <- 33052
  low <- 40389
  for (byte in as.integer(charToRaw(enc2utf8(payload)))) {
    low <- bitwXor(as.integer(low), as.integer(byte))
    low_product <- low * 403
    next_low <- low_product %% 65536
    carry <- floor(low_product / 65536)
    next_high <- (high * 403 + low * 256 + carry) %% 65536
    high <- next_high
    low <- next_low
  }
  sprintf("%04x%04x", as.integer(high), as.integer(low))
}

cases <- read_relation("cases.csv")
states_all <- read_relation("states.csv")
roster_all <- read_relation("cluster_roster.csv")
priors_all <- read_relation("priors.csv")
candidates_all <- read_relation("regularizers.csv")
records_all <- read_relation("records.csv")

solve_case <- function(case_row) {
  case_id <- case_row$case_id[[1L]]
  edge_floor <- case_row$edge_probability_floor[[1L]]
  safety_floor <- case_row$safety_floor[[1L]]
  ess_floor <- case_row$ess_floor[[1L]]
  safety_weight <- case_row$safety_weight[[1L]]
  robustness_scale <- case_row$robustness_scale[[1L]]
  cv_penalty <- case_row$cv_penalty[[1L]]
  instability_penalty <- case_row$cycle_instability_penalty[[1L]]
  max_deleted <- as.integer(case_row$max_deleted_clusters[[1L]])
  case_parameters <- c(
    edge_floor,
    safety_floor,
    ess_floor,
    safety_weight,
    robustness_scale,
    cv_penalty,
    instability_penalty,
    max_deleted
  )

  states <- sort(
    states_all$state_id[states_all$case_id == case_id],
    method = "radix"
  )
  state_count <- length(states)
  state_index <- setNames(seq_along(states), states)
  roster <- roster_all[roster_all$case_id == case_id, , drop = FALSE]
  roster <- roster[
    order(as.integer(roster$cluster)),
    ,
    drop = FALSE
  ]
  clusters <- as.integer(roster$cluster)
  cluster_count <- length(clusters)
  cluster_index <- setNames(seq_along(clusters), as.character(clusters))
  exposures <- as.numeric(roster$exposure_weight)
  stresses <- as.numeric(roster$stress_score)

  candidates <- candidates_all[
    candidates_all$case_id == case_id,
    ,
    drop = FALSE
  ]
  candidates <- candidates[
    order(
      as.integer(candidates$candidate_rank),
      candidates$candidate_id,
      method = "radix"
    ),
    ,
    drop = FALSE
  ]
  candidate_count <- nrow(candidates)

  records <- records_all[
    records_all$case_id == case_id,
    ,
    drop = FALSE
  ]
  records <- records[order(records$event_id, method = "radix"), , drop = FALSE]
  policies <- sort(unique(records$policy_id), method = "radix")
  policy_count <- length(policies)
  policy_index <- setNames(seq_along(policies), policies)

  if (
    state_count < 1L ||
      cluster_count < 5L ||
      policy_count < 1L ||
      candidate_count < 1L ||
      any(!is.finite(case_parameters)) ||
      !is.finite(max_deleted) ||
      max_deleted < 1L ||
      anyDuplicated(states) ||
      anyDuplicated(clusters) ||
      anyDuplicated(candidates$candidate_rank) ||
      anyDuplicated(candidates$candidate_id) ||
      any(!is.finite(exposures)) ||
      any(exposures <= 0) ||
      any(!is.finite(stresses)) ||
      any(!is.finite(candidates$lambda)) ||
      any(candidates$lambda < 0) ||
      any(!is.finite(candidates$covariance_ridge)) ||
      any(candidates$covariance_ridge < 0) ||
      any(!is.finite(candidates$support_z)) ||
      any(candidates$support_z < 0)
  ) {
    stop(paste(case_id, "has an invalid case domain"))
  }

  prior_rows <- priors_all[
    priors_all$case_id == case_id,
    ,
    drop = FALSE
  ]
  prior_mass <- matrix(NA_real_, state_count, state_count)
  prior_value <- matrix(NA_real_, state_count, state_count)
  prior_keys <- paste(
    prior_rows$from_state,
    prior_rows$to_state,
    sep = "\x1f"
  )
  if (
    nrow(prior_rows) != state_count ^ 2 ||
      anyDuplicated(prior_keys)
  ) {
    stop(paste(case_id, "has an invalid edge prior"))
  }
  for (row_index in seq_len(nrow(prior_rows))) {
    row <- prior_rows[row_index, , drop = FALSE]
    source <- state_index[[row$from_state[[1L]]]]
    destination <- state_index[[row$to_state[[1L]]]]
    prior_mass[source, destination] <- row$prior_mass[[1L]]
    prior_value[source, destination] <- row$prior_value[[1L]]
  }
  if (
    anyNA(prior_mass) ||
      anyNA(prior_value) ||
      any(!is.finite(prior_mass)) ||
      any(prior_mass <= 0)
  ) {
    stop(paste(case_id, "has an invalid edge prior"))
  }

  edge_mass <- array(
    0,
    dim = c(policy_count, cluster_count, state_count, state_count)
  )
  edge_weighted <- edge_mass
  edge_squared <- edge_mass
  return_numerator <- matrix(0, policy_count, cluster_count)
  return_denominator <- matrix(0, policy_count, cluster_count)
  observed_grid <- matrix(FALSE, policy_count, cluster_count)
  for (row_index in seq_len(nrow(records))) {
    row <- records[row_index, , drop = FALSE]
    policy_position <- policy_index[[row$policy_id[[1L]]]]
    cluster_position <- cluster_index[[
      as.character(as.integer(row$cluster[[1L]]))
    ]]
    source <- state_index[[row$state_id[[1L]]]]
    destination <- state_index[[row$next_state[[1L]]]]
    weight <- row$target_prob[[1L]] / row$behavior_prob[[1L]]
    utility <- row$reward[[1L]] - row$cost[[1L]]
    if (
      is.null(cluster_position) ||
        is.null(source) ||
        is.null(destination) ||
        !is.finite(weight) ||
        weight <= 0 ||
        !is.finite(utility)
    ) {
      stop(paste(case_id, "has an invalid record"))
    }
    observed_grid[policy_position, cluster_position] <- TRUE
    edge_mass[
      policy_position,
      cluster_position,
      source,
      destination
    ] <- edge_mass[
      policy_position,
      cluster_position,
      source,
      destination
    ] + weight
    edge_weighted[
      policy_position,
      cluster_position,
      source,
      destination
    ] <- edge_weighted[
      policy_position,
      cluster_position,
      source,
      destination
    ] + weight * utility
    edge_squared[
      policy_position,
      cluster_position,
      source,
      destination
    ] <- edge_squared[
      policy_position,
      cluster_position,
      source,
      destination
    ] + weight ^ 2
    return_numerator[policy_position, cluster_position] <- (
      return_numerator[policy_position, cluster_position] + weight * utility
    )
    return_denominator[policy_position, cluster_position] <- (
      return_denominator[policy_position, cluster_position] + weight
    )
  }
  if (any(!observed_grid) || any(return_denominator <= 0)) {
    stop(paste(case_id, "has an incomplete policy-cluster grid"))
  }
  cluster_return <- return_numerator / return_denominator

  transition_model <- array(
    0,
    dim = c(
      candidate_count,
      policy_count,
      cluster_count,
      state_count,
      state_count
    )
  )
  edge_value_model <- transition_model
  for (candidate_position in seq_len(candidate_count)) {
    regularizer <- candidates$lambda[[candidate_position]]
    for (policy_position in seq_len(policy_count)) {
      for (cluster_position in seq_len(cluster_count)) {
        for (source in seq_len(state_count)) {
          masses <- numeric(state_count)
          for (destination in seq_len(state_count)) {
            empirical_mass <- edge_mass[
              policy_position,
              cluster_position,
              source,
              destination
            ]
            smoothed_mass <- empirical_mass + (
              regularizer * prior_mass[source, destination]
            )
            masses[[destination]] <- smoothed_mass
            edge_value_model[
              candidate_position,
              policy_position,
              cluster_position,
              source,
              destination
            ] <- (
              edge_weighted[
                policy_position,
                cluster_position,
                source,
                destination
              ] +
                regularizer *
                  prior_mass[source, destination] *
                  prior_value[source, destination]
            ) / max(smoothed_mass, 1e-300)
          }
          transition_model[
            candidate_position,
            policy_position,
            cluster_position,
            source,
            seq_len(state_count)
          ] <- masses / sum(masses)
        }
      }
    }
  }

  normalized_exposures <- function(retained_positions) {
    values <- exposures[retained_positions]
    values / sum(values)
  }

  pooled_transition <- function(
    candidate_position,
    policy_position,
    retained_positions
  ) {
    cluster_weights <- normalized_exposures(retained_positions)
    output <- matrix(0, state_count, state_count)
    for (source in seq_len(state_count)) {
      for (destination in seq_len(state_count)) {
        output[source, destination] <- sum(
          cluster_weights * transition_model[
            candidate_position,
            policy_position,
            retained_positions,
            source,
            destination
          ]
        )
      }
    }
    output
  }

  support_lower <- function(
    candidate_position,
    policy_position,
    retained_positions
  ) {
    cluster_weights <- normalized_exposures(retained_positions)
    support_z <- candidates$support_z[[candidate_position]]
    output <- matrix(0, state_count, state_count)
    for (source in seq_len(state_count)) {
      for (destination in seq_len(state_count)) {
        values <- transition_model[
          candidate_position,
          policy_position,
          retained_positions,
          source,
          destination
        ]
        center <- sum(cluster_weights * values)
        variance <- sum(cluster_weights * (values - center) ^ 2)
        output[source, destination] <- (
          center - support_z * sqrt(max(variance, 0))
        )
      }
    }
    output
  }

  metric_cache <- new.env(hash = TRUE, parent = emptyenv())
  cv_cache <- new.env(hash = TRUE, parent = emptyenv())
  refit_cache <- new.env(hash = TRUE, parent = emptyenv())

  policy_metric <- function(
    candidate_position,
    policy_position,
    retained_positions
  ) {
    key <- paste(
      candidate_position,
      policy_position,
      paste(retained_positions, collapse = "."),
      sep = "|"
    )
    if (exists(key, envir = metric_cache, inherits = FALSE)) {
      return(get(key, envir = metric_cache, inherits = FALSE))
    }
    support <- support_lower(
      candidate_position,
      policy_position,
      retained_positions
    )
    threshold_code <- decision_code(edge_floor)
    adjacency <- lapply(
      seq_len(state_count),
      function(source) {
        which(decision_code(support[source, ]) >= threshold_code)
      }
    )
    cycles <- simple_cycles(state_count, adjacency)
    if (length(cycles) == 0L) {
      assign(key, NULL, envir = metric_cache)
      return(NULL)
    }
    cluster_weights <- normalized_exposures(retained_positions)
    ridge <- candidates$covariance_ridge[[candidate_position]]
    cycle_rows <- lapply(
      cycles,
      function(cycle) {
        destinations <- c(cycle[-1L], cycle[[1L]])
        cluster_means <- vapply(
          retained_positions,
          function(cluster_position) {
            values <- mapply(
              function(source, destination) {
                edge_value_model[
                  candidate_position,
                  policy_position,
                  cluster_position,
                  source,
                  destination
                ]
              },
              cycle,
              destinations
            )
            mean(values)
          },
          numeric(1)
        )
        center <- sum(cluster_weights * cluster_means)
        variance <- sum(
          cluster_weights * (cluster_means - center) ^ 2
        )
        covariance <- sqrt(
          max(variance + ridge / length(cycle), 0)
        )
        edge_ess <- vapply(
          seq_along(cycle),
          function(edge_index) {
            source <- cycle[[edge_index]]
            destination <- destinations[[edge_index]]
            mass <- sum(
              edge_mass[
                policy_position,
                retained_positions,
                source,
                destination
              ]
            )
            squared <- sum(
              edge_squared[
                policy_position,
                retained_positions,
                source,
                destination
              ]
            )
            if (squared > 0) mass ^ 2 / squared else 0
          },
          numeric(1)
        )
        harmonic_ess <- if (all(edge_ess > 0)) {
          length(edge_ess) / sum(1 / edge_ess)
        } else {
          0
        }
        list(
          cycle = cycle,
          code = cycle_code(cycle, states),
          center = center,
          covariance = covariance,
          safety = center - robustness_scale * covariance,
          ess = harmonic_ess,
          minimum_support = min(
            mapply(
              function(source, destination) {
                support[source, destination]
              },
              cycle,
              destinations
            )
          )
        )
      }
    )
    safety_codes <- vapply(
      cycle_rows,
      function(row) decision_code(row$safety),
      numeric(1)
    )
    critical_pool <- cycle_rows[safety_codes == min(safety_codes)]
    critical_codes <- vapply(
      critical_pool,
      function(row) row$code,
      character(1)
    )
    critical <- critical_pool[[
      order(critical_codes, method = "radix")[[1L]]
    ]]

    returns <- cluster_return[policy_position, retained_positions]
    return_center <- sum(cluster_weights * returns)
    lower_sd <- sqrt(
      sum(cluster_weights * pmax(return_center - returns, 0) ^ 2)
    )
    robust_return <- return_center - robustness_scale * lower_sd
    result <- list(
      policy = policies[[policy_position]],
      score = robust_return + safety_weight * critical$safety,
      robust_return = robust_return,
      safety = critical$safety,
      cycle = critical$cycle,
      critical_cycle = critical$code,
      cycle_length = length(critical$cycle),
      cycle_center = critical$center,
      covariance = critical$covariance,
      ess = critical$ess,
      support_count = sum(
        decision_code(support) >= threshold_code
      ),
      minimum_support = critical$minimum_support
    )
    assign(key, result, envir = metric_cache)
    result
  }

  candidate_cv_loss <- function(
    candidate_position,
    retained_positions
  ) {
    key <- paste(
      candidate_position,
      paste(retained_positions, collapse = "."),
      sep = "|"
    )
    if (exists(key, envir = cv_cache, inherits = FALSE)) {
      return(get(key, envir = cv_cache, inherits = FALSE))
    }
    contributions <- numeric(0)
    contribution_weights <- numeric(0)
    for (policy_position in seq_len(policy_count)) {
      for (holdout in retained_positions) {
        training <- retained_positions[retained_positions != holdout]
        train_transition <- pooled_transition(
          candidate_position,
          policy_position,
          training
        )
        train_support <- support_lower(
          candidate_position,
          policy_position,
          training
        )
        metric <- policy_metric(
          candidate_position,
          policy_position,
          training
        )
        if (is.null(metric)) {
          invalid <- (
            1000000000 +
              as.integer(candidates$candidate_rank[[candidate_position]])
          )
          assign(key, invalid, envir = cv_cache)
          return(invalid)
        }
        masses <- matrix(
          edge_mass[
            policy_position,
            holdout,
            seq_len(state_count),
            seq_len(state_count)
          ],
          nrow = state_count,
          ncol = state_count
        )
        nll <- sum(masses * -log(pmax(train_transition, 1e-300))) / (
          sum(masses)
        )
        held_transition <- matrix(
          transition_model[
            candidate_position,
            policy_position,
            holdout,
            seq_len(state_count),
            seq_len(state_count)
          ],
          nrow = state_count,
          ncol = state_count
        )
        support_error <- mean(
          (
            decision_code(train_support) >= decision_code(edge_floor)
          ) != (
            decision_code(held_transition) >= decision_code(edge_floor)
          )
        )
        cycle <- metric$cycle
        destinations <- c(cycle[-1L], cycle[[1L]])
        held_values <- mapply(
          function(source, destination) {
            edge_value_model[
              candidate_position,
              policy_position,
              holdout,
              source,
              destination
            ]
          },
          cycle,
          destinations
        )
        instability <- (mean(held_values) - metric$cycle_center) ^ 2
        contributions <- c(
          contributions,
          nll +
            cv_penalty * support_error +
            instability_penalty * instability
        )
        contribution_weights <- c(
          contribution_weights,
          exposures[[holdout]] * (1 + 0.2 * abs(stresses[[holdout]]))
        )
      }
    }
    center <- sum(contribution_weights * contributions) / (
      sum(contribution_weights)
    )
    spread <- sqrt(
      sum(contribution_weights * (contributions - center) ^ 2) / (
        sum(contribution_weights)
      )
    )
    value <- center + 0.15 * spread
    assign(key, value, envir = cv_cache)
    value
  }

  select_candidate <- function(retained_positions) {
    scores <- vapply(
      seq_len(candidate_count),
      function(candidate_position) {
        candidate_cv_loss(candidate_position, retained_positions)
      },
      numeric(1)
    )
    candidate_positions <- which(
      decision_code(scores) == min(decision_code(scores))
    )
    ordering <- order(
      as.integer(candidates$candidate_rank[candidate_positions]),
      candidates$candidate_id[candidate_positions],
      method = "radix"
    )
    position <- candidate_positions[[ordering[[1L]]]]
    list(
      position = position,
      id = candidates$candidate_id[[position]],
      rank = as.integer(candidates$candidate_rank[[position]]),
      cv_loss = scores[[position]]
    )
  }

  refit <- function(retained_positions) {
    key <- paste(retained_positions, collapse = ".")
    if (exists(key, envir = refit_cache, inherits = FALSE)) {
      return(get(key, envir = refit_cache, inherits = FALSE))
    }
    candidate <- select_candidate(retained_positions)
    policy_rows <- lapply(
      seq_len(policy_count),
      function(policy_position) {
        policy_metric(
          candidate$position,
          policy_position,
          retained_positions
        )
      }
    )
    if (any(vapply(policy_rows, is.null, logical(1)))) {
      stop(paste(case_id, "selected an acyclic candidate"))
    }
    feasible <- Filter(
      function(row) {
        decision_code(row$safety) >= decision_code(safety_floor) &&
          decision_code(row$ess) >= decision_code(ess_floor)
      },
      policy_rows
    )
    pool <- if (length(feasible) > 0L) feasible else policy_rows
    codes <- vapply(
      pool,
      function(row) decision_code(row$score),
      numeric(1)
    )
    pool <- pool[codes == max(codes)]
    codes <- vapply(
      pool,
      function(row) decision_code(row$safety),
      numeric(1)
    )
    pool <- pool[codes == max(codes)]
    codes <- vapply(
      pool,
      function(row) decision_code(row$ess),
      numeric(1)
    )
    pool <- pool[codes == max(codes)]
    policy_ids <- vapply(pool, function(row) row$policy, character(1))
    selected <- pool[[order(policy_ids, method = "radix")[[1L]]]]
    result <- list(
      selected = selected,
      feasible_count = length(feasible),
      candidate = candidate
    )
    assign(key, result, envir = refit_cache)
    result
  }

  full_positions <- seq_along(clusters)
  full <- refit(full_positions)
  selected <- full$selected
  full_identity <- paste(
    full$candidate$id,
    selected$policy,
    selected$critical_cycle,
    sep = "\x1f"
  )
  scenarios <- list()
  upper <- min(max_deleted, cluster_count - 4L)
  if (upper >= 1L) {
    for (size in seq_len(upper)) {
      scenarios <- c(
        scenarios,
        combn(clusters, size, simplify = FALSE)
      )
    }
  }

  deletion_parts <- character(0)
  changes <- 0L
  worst_safety <- Inf
  worst_code <- 0L
  maximum_covariance <- -Inf
  checksum <- 0
  for (scenario in scenarios) {
    scenario_code <- as.integer(
      sum(2 ^ (match(scenario, clusters) - 1L))
    )
    retained_positions <- which(!clusters %in% scenario)
    fitted <- refit(retained_positions)
    row <- fitted$selected
    identity <- paste(
      fitted$candidate$id,
      row$policy,
      row$critical_cycle,
      sep = "\x1f"
    )
    changes <- changes + as.integer(identity != full_identity)
    deletion_parts <- c(
      deletion_parts,
      paste(
        scenario_code,
        fitted$candidate$id,
        row$policy,
        row$critical_cycle,
        sep = ":"
      )
    )
    if (
      decision_code(row$safety) < decision_code(worst_safety) ||
        (
          decision_code(row$safety) == decision_code(worst_safety) &&
            scenario_code < worst_code
        )
    ) {
      worst_safety <- row$safety
      worst_code <- scenario_code
    }
    maximum_covariance <- max(maximum_covariance, row$covariance)
    checksum <- checksum + scenario_code * (
      11 * fitted$candidate$rank +
        13 * decision_code(fitted$candidate$cv_loss) +
        17 * decision_code(row$score) +
        19 * decision_code(row$robust_return) +
        23 * decision_code(row$safety) +
        29 * decision_code(row$ess) +
        31 * row$support_count +
        37 * decision_code(row$minimum_support) +
        41 * decision_code(row$covariance)
    )
  }
  checksum <- checksum %% 2147483647
  deletion_code <- paste(deletion_parts, collapse = "|")
  integer_text <- function(value) sprintf("%.0f", value)
  payload <- paste(
    case_id,
    full$candidate$id,
    selected$policy,
    selected$critical_cycle,
    deletion_code,
    integer_text(decision_code(selected$score)),
    integer_text(decision_code(selected$robust_return)),
    integer_text(decision_code(selected$safety)),
    integer_text(decision_code(selected$covariance)),
    integer_text(decision_code(selected$ess)),
    integer_text(selected$support_count),
    integer_text(decision_code(selected$minimum_support)),
    integer_text(decision_code(full$candidate$cv_loss)),
    integer_text(changes),
    integer_text(worst_code),
    integer_text(checksum),
    sep = "|"
  )

  data.frame(
    case_id = case_id,
    selected_candidate = full$candidate$id,
    selected_policy = selected$policy,
    feasible_count = full$feasible_count,
    policy_score = selected$score,
    robust_policy_return = selected$robust_return,
    minimum_cycle_mean = selected$safety,
    critical_cycle = selected$critical_cycle,
    critical_cycle_length = selected$cycle_length,
    cycle_covariance_penalty = selected$covariance,
    effective_sample_size = selected$ess,
    support_edge_count = selected$support_count,
    minimum_edge_support = selected$minimum_support,
    cv_loss = full$candidate$cv_loss,
    deletion_code = deletion_code,
    deletion_change_count = changes,
    worst_deletion_safety = worst_safety,
    worst_deletion_scenario_code = worst_code,
    maximum_deletion_covariance = maximum_covariance,
    stability_checksum = checksum,
    audit_signature = fnv1a(payload),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

cases <- cases[order(cases$case_id, method = "radix"), , drop = FALSE]
rows <- lapply(
  seq_len(nrow(cases)),
  function(index) solve_case(cases[index, , drop = FALSE])
)
output <- do.call(rbind, rows)
dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
write.table(
  output,
  output_file,
  sep = ",",
  row.names = FALSE,
  col.names = TRUE,
  quote = FALSE,
  na = ""
)
