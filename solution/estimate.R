args <- commandArgs(trailingOnly = TRUE)
data_dir <- if (length(args) >= 1L) args[[1]] else "/app/data"
output_file <- if (length(args) >= 2L) {
  args[[2]]
} else {
  "/app/outputs/results.csv"
}
Sys.setlocale("LC_COLLATE", "C")
options(digits = 17, scipen = 999)
tolerance <- 1e-12

read_relation <- function(name) {
  read.csv(
    file.path(data_dir, name),
    stringsAsFactors = FALSE,
    check.names = FALSE
  )
}

population_sd <- function(values) {
  center <- mean(values)
  sqrt(mean((values - center) ^ 2))
}

cycle_code <- function(cycle, states) {
  paste(states[c(cycle, cycle[[1]])], collapse = ">")
}

simple_cycles <- function(states, adjacency) {
  cycles <- list()
  state_count <- length(states)
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

cases <- read_relation("cases.csv")
states_all <- read_relation("states.csv")
priors_all <- read_relation("priors.csv")
regularizers_all <- read_relation("regularizers.csv")
records_all <- read_relation("records.csv")

solve_case <- function(case_row) {
  case_id <- case_row$case_id[[1]]
  edge_floor <- case_row$edge_probability_floor[[1]]
  safety_floor <- case_row$safety_floor[[1]]
  ess_floor <- case_row$ess_floor[[1]]
  safety_weight <- case_row$safety_weight[[1]]
  robustness_scale <- case_row$robustness_scale[[1]]
  cv_penalty <- case_row$cv_penalty[[1]]
  max_deleted <- as.integer(case_row$max_deleted_clusters[[1]])

  states <- sort(
    states_all$state_id[states_all$case_id == case_id],
    method = "radix"
  )
  state_count <- length(states)
  state_index <- setNames(seq_along(states), states)
  prior_rows <- priors_all[priors_all$case_id == case_id, , drop = FALSE]
  lambda_rows <- regularizers_all[
    regularizers_all$case_id == case_id,
    ,
    drop = FALSE
  ]
  lambda_rows <- lambda_rows[
    order(lambda_rows$lambda_rank),
    ,
    drop = FALSE
  ]
  records <- records_all[records_all$case_id == case_id, , drop = FALSE]
  policies <- sort(unique(records$policy_id), method = "radix")
  clusters <- sort(unique(as.integer(records$cluster)))
  policy_count <- length(policies)
  cluster_count <- length(clusters)
  lambda_count <- nrow(lambda_rows)
  policy_index <- setNames(seq_along(policies), policies)
  cluster_index <- setNames(seq_along(clusters), as.character(clusters))
  policy_rank <- setNames(seq_along(policies), policies)

  prior_mass <- matrix(NA_real_, state_count, state_count)
  prior_value <- matrix(NA_real_, state_count, state_count)
  for (row_index in seq_len(nrow(prior_rows))) {
    row <- prior_rows[row_index, , drop = FALSE]
    source <- state_index[[row$from_state[[1]]]]
    destination <- state_index[[row$to_state[[1]]]]
    prior_mass[source, destination] <- row$prior_mass[[1]]
    prior_value[source, destination] <- row$prior_value[[1]]
  }
  if (anyNA(prior_mass) || anyNA(prior_value)) {
    stop(paste(case_id, "has an incomplete edge prior"))
  }

  edge_mass <- array(
    0,
    dim = c(policy_count, cluster_count, state_count, state_count)
  )
  edge_weighted <- array(
    0,
    dim = c(policy_count, cluster_count, state_count, state_count)
  )
  edge_squared <- array(
    0,
    dim = c(policy_count, cluster_count, state_count, state_count)
  )
  return_numerator <- matrix(0, policy_count, cluster_count)
  return_denominator <- matrix(0, policy_count, cluster_count)
  for (row_index in seq_len(nrow(records))) {
    row <- records[row_index, , drop = FALSE]
    policy_position <- policy_index[[row$policy_id[[1]]]]
    cluster_position <- cluster_index[[
      as.character(as.integer(row$cluster[[1]]))
    ]]
    source <- state_index[[row$state_id[[1]]]]
    destination <- state_index[[row$next_state[[1]]]]
    weight <- row$target_prob[[1]] / row$behavior_prob[[1]]
    utility <- row$reward[[1]] - row$cost[[1]]
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
  cluster_return <- return_numerator / return_denominator

  transition_model <- array(
    0,
    dim = c(
      lambda_count,
      policy_count,
      cluster_count,
      state_count,
      state_count
    )
  )
  edge_value_model <- transition_model
  for (lambda_position in seq_len(lambda_count)) {
    regularizer <- lambda_rows$lambda[[lambda_position]]
    for (policy_position in seq_len(policy_count)) {
      for (cluster_position in seq_len(cluster_count)) {
        for (source in seq_len(state_count)) {
          masses <- numeric(state_count)
          for (destination in seq_len(state_count)) {
            mass <- edge_mass[
              policy_position,
              cluster_position,
              source,
              destination
            ]
            denominator <- (
              mass + regularizer * prior_mass[source, destination]
            )
            masses[[destination]] <- denominator
            edge_value_model[
              lambda_position,
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
            ) / max(denominator, 1e-300)
          }
          transition_model[
            lambda_position,
            policy_position,
            cluster_position,
            source,
            seq_len(state_count)
          ] <- masses / sum(masses)
        }
      }
    }
  }

  pooled_transition <- function(
    lambda_position,
    policy_position,
    retained_positions
  ) {
    output <- matrix(0, state_count, state_count)
    for (source in seq_len(state_count)) {
      for (destination in seq_len(state_count)) {
        output[source, destination] <- mean(
          transition_model[
            lambda_position,
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

  lambda_cv_loss <- function(lambda_position, retained_positions) {
    losses <- numeric(0)
    for (policy_position in seq_len(policy_count)) {
      for (holdout in retained_positions) {
        training <- retained_positions[retained_positions != holdout]
        transition <- pooled_transition(
          lambda_position,
          policy_position,
          training
        )
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
        losses <- c(
          losses,
          sum(masses * -log(pmax(transition, 1e-300))) / sum(masses)
        )
      }
    }
    mean(losses) + cv_penalty * population_sd(losses)
  }

  select_lambda <- function(retained_positions) {
    scores <- vapply(
      seq_len(lambda_count),
      function(lambda_position) {
        lambda_cv_loss(lambda_position, retained_positions)
      },
      numeric(1)
    )
    best <- min(scores)
    candidates <- which(abs(scores - best) <= tolerance)
    candidate_ranks <- as.integer(lambda_rows$lambda_rank[candidates])
    position <- candidates[[which.min(candidate_ranks)]]
    list(
      position = position,
      id = lambda_rows$lambda_id[[position]],
      rank = as.integer(lambda_rows$lambda_rank[[position]]),
      cv_loss = scores[[position]]
    )
  }

  policy_metric <- function(
    lambda_position,
    policy_position,
    retained_positions
  ) {
    transition <- pooled_transition(
      lambda_position,
      policy_position,
      retained_positions
    )
    robust_edge <- matrix(0, state_count, state_count)
    for (source in seq_len(state_count)) {
      for (destination in seq_len(state_count)) {
        values <- edge_value_model[
          lambda_position,
          policy_position,
          retained_positions,
          source,
          destination
        ]
        robust_edge[source, destination] <- (
          mean(values) - robustness_scale * population_sd(values)
        )
      }
    }
    adjacency <- lapply(
      seq_len(state_count),
      function(source) which(transition[source, ] >= edge_floor)
    )
    cycles <- simple_cycles(states, adjacency)
    if (length(cycles) == 0L) {
      stop(paste(case_id, "has a fitted graph without a cycle"))
    }
    cycle_rows <- lapply(
      cycles,
      function(cycle) {
        destinations <- c(cycle[-1], cycle[[1]])
        values <- mapply(
          function(source, destination) {
            robust_edge[source, destination]
          },
          cycle,
          destinations
        )
        minimum_ess <- Inf
        for (edge_index in seq_along(cycle)) {
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
          edge_ess <- if (squared > 0) mass ^ 2 / squared else 0
          minimum_ess <- min(minimum_ess, edge_ess)
        }
        list(
          code = cycle_code(cycle, states),
          safety = mean(values),
          ess = minimum_ess
        )
      }
    )
    safety_values <- vapply(
      cycle_rows,
      function(row) row$safety,
      numeric(1)
    )
    best_safety <- min(safety_values)
    candidates <- cycle_rows[
      abs(safety_values - best_safety) <= tolerance
    ]
    codes <- vapply(candidates, function(row) row$code, character(1))
    critical <- candidates[[order(codes, method = "radix")[[1]]]]

    returns <- cluster_return[policy_position, retained_positions]
    center <- mean(returns)
    downside <- sqrt(mean(pmax(center - returns, 0) ^ 2))
    robust_return <- center - robustness_scale * downside
    list(
      policy = policies[[policy_position]],
      score = robust_return + safety_weight * critical$safety,
      robust_return = robust_return,
      safety = critical$safety,
      critical_cycle = critical$code,
      ess = critical$ess
    )
  }

  refit <- function(retained_positions) {
    lambda_choice <- select_lambda(retained_positions)
    policy_rows <- lapply(
      seq_len(policy_count),
      function(policy_position) {
        policy_metric(
          lambda_choice$position,
          policy_position,
          retained_positions
        )
      }
    )
    feasible <- Filter(
      function(row) {
        row$safety >= safety_floor && row$ess >= ess_floor
      },
      policy_rows
    )
    pool <- if (length(feasible) > 0L) feasible else policy_rows
    scores <- vapply(pool, function(row) row$score, numeric(1))
    best <- max(scores)
    pool <- pool[abs(scores - best) <= tolerance]
    safety_values <- vapply(pool, function(row) row$safety, numeric(1))
    best <- max(safety_values)
    pool <- pool[abs(safety_values - best) <= tolerance]
    ess_values <- vapply(pool, function(row) row$ess, numeric(1))
    best <- max(ess_values)
    pool <- pool[abs(ess_values - best) <= tolerance]
    policy_ids <- vapply(pool, function(row) row$policy, character(1))
    selected <- pool[[order(policy_ids, method = "radix")[[1]]]]
    list(
      selected = selected,
      feasible_count = length(feasible),
      lambda_id = lambda_choice$id,
      lambda_rank = lambda_choice$rank,
      cv_loss = lambda_choice$cv_loss
    )
  }

  full_positions <- seq_along(clusters)
  full <- refit(full_positions)
  selected <- full$selected
  deletion_scenarios <- list()
  upper <- min(max_deleted, cluster_count - 2L)
  if (upper >= 1L) {
    for (size in seq_len(upper)) {
      deletion_scenarios <- c(
        deletion_scenarios,
        combn(clusters, size, simplify = FALSE)
      )
    }
  }
  full_identity <- paste(
    full$lambda_id,
    selected$policy,
    selected$critical_cycle,
    sep = "\x1f"
  )
  deletion_parts <- character(0)
  deletion_change_count <- 0L
  worst_safety <- Inf
  worst_code <- 0L
  stability_checksum <- 0
  for (scenario_index in seq_along(deletion_scenarios)) {
    scenario <- deletion_scenarios[[scenario_index]]
    scenario_code <- as.integer(
      sum(2 ^ (match(scenario, clusters) - 1L))
    )
    retained_positions <- which(!clusters %in% scenario)
    deleted_fit <- refit(retained_positions)
    row <- deleted_fit$selected
    identity <- paste(
      deleted_fit$lambda_id,
      row$policy,
      row$critical_cycle,
      sep = "\x1f"
    )
    deletion_change_count <- deletion_change_count + as.integer(
      identity != full_identity
    )
    deletion_parts <- c(
      deletion_parts,
      paste(
        scenario_code,
        deleted_fit$lambda_id,
        row$policy,
        row$critical_cycle,
        sep = ":"
      )
    )
    if (row$safety < worst_safety - tolerance) {
      worst_safety <- row$safety
      worst_code <- scenario_code
    }
    stability_checksum <- stability_checksum + scenario_index * (
      row$score +
        2 * row$robust_return +
        3 * row$safety +
        5 * row$ess +
        7 * deleted_fit$cv_loss +
        11 * scenario_code +
        13 * deleted_fit$lambda_rank +
        17 * policy_rank[[row$policy]]
    )
  }
  deletion_code <- paste(deletion_parts, collapse = "|")
  numeric_values <- c(
    selected$score,
    selected$robust_return,
    selected$safety,
    selected$ess,
    full$cv_loss,
    stability_checksum
  )
  numeric_codes <- vapply(
    numeric_values,
    function(value) sprintf("%.0f", round(value * 100000000)),
    character(1)
  )
  payload <- paste(
    case_id,
    full$lambda_id,
    selected$policy,
    selected$critical_cycle,
    deletion_code,
    numeric_codes[[1]],
    numeric_codes[[2]],
    numeric_codes[[3]],
    numeric_codes[[4]],
    numeric_codes[[5]],
    deletion_change_count,
    worst_code,
    numeric_codes[[6]],
    sep = "|"
  )
  accumulator <- 0
  bytes <- as.integer(charToRaw(enc2utf8(payload)))
  for (position in seq_along(bytes)) {
    accumulator <- (
      263 * accumulator + bytes[[position]] + position
    ) %% 2147483647
  }
  data.frame(
    case_id = case_id,
    selected_lambda = full$lambda_id,
    selected_policy = selected$policy,
    feasible_count = full$feasible_count,
    policy_score = selected$score,
    robust_policy_return = selected$robust_return,
    minimum_cycle_mean = selected$safety,
    critical_cycle = selected$critical_cycle,
    effective_sample_size = selected$ess,
    cv_loss = full$cv_loss,
    deletion_code = deletion_code,
    deletion_change_count = deletion_change_count,
    worst_deletion_safety = worst_safety,
    worst_deletion_scenario_code = worst_code,
    stability_checksum = stability_checksum,
    audit_signature = sprintf("%08x", as.integer(accumulator)),
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
