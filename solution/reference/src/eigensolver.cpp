#include "emsolve/eigensolver.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <vector>

#include <Eigen/Eigenvalues>

#include "emsolve/checkpoint.hpp"

namespace emsolve {

namespace {

constexpr double kClusterRelGap = 1e-7;
constexpr double kRepeatedSubgroupTol = 1e-10;
constexpr double kProbeNormTol = 1e-12;
constexpr double kMOrthonormTol = 1e-8;
constexpr double kRayleighRelTol = 1e-7;

static FactorizationCache g_cache;

static double m_inner(const Eigen::MatrixXd& M, const Eigen::VectorXd& a,
                      const Eigen::VectorXd& b) {
  return a.dot(M * b);
}

static double m_norm(const Eigen::MatrixXd& M, const Eigen::VectorXd& v) {
  return std::sqrt(std::max(0.0, m_inner(M, v, v)));
}

static double rayleigh_quotient(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M,
                                const Eigen::VectorXd& x) {
  const double denom = m_inner(M, x, x);
  if (denom <= 0.0) throw std::runtime_error("non-positive M-norm in Rayleigh quotient");
  return x.dot(K * x) / denom;
}

static void fix_sign(Eigen::VectorXd& v) {
  for (int i = 0; i < v.size(); ++i) {
    if (std::abs(v(i)) > kProbeNormTol) {
      if (v(i) < 0.0) v *= -1.0;
      return;
    }
  }
}

static double relative_gap(double a, double b) {
  return std::abs(a - b) / std::max({std::abs(a), std::abs(b), 1.0});
}

static std::vector<int> cluster_ids_sorted(const std::vector<double>& lambdas) {
  std::vector<int> order(lambdas.size());
  for (size_t i = 0; i < order.size(); ++i) order[i] = static_cast<int>(i);
  std::sort(order.begin(), order.end(),
            [&](int a, int b) { return lambdas[static_cast<size_t>(a)] < lambdas[static_cast<size_t>(b)]; });

  std::vector<int> cluster(lambdas.size(), 0);
  int cid = 0;
  for (size_t i = 0; i < order.size(); ++i) {
    if (i > 0 &&
        relative_gap(lambdas[static_cast<size_t>(order[i])],
                     lambdas[static_cast<size_t>(order[i - 1])]) > kClusterRelGap) {
      ++cid;
    }
    cluster[static_cast<size_t>(order[i])] = cid;
  }
  return cluster;
}

static std::vector<std::vector<size_t>> repeated_subgroups_in_cluster(
    const std::vector<double>& lambdas, const std::vector<int>& cluster_ids, int cid) {
  std::vector<size_t> members;
  for (size_t i = 0; i < lambdas.size(); ++i) {
    if (cluster_ids[i] == cid) members.push_back(i);
  }
  std::sort(members.begin(), members.end(),
            [&](size_t a, size_t b) { return lambdas[a] < lambdas[b]; });

  std::vector<std::vector<size_t>> groups;
  if (members.empty()) return groups;

  std::vector<size_t> cur{members.front()};
  double lam0 = lambdas[members.front()];
  double scale = std::max(1.0, std::abs(lam0));
  for (size_t k = 1; k < members.size(); ++k) {
    const size_t idx = members[k];
    const double lam = lambdas[idx];
    if (std::max(std::abs(lam - lam0), std::abs(lam - lambdas[cur.front()])) <=
        kRepeatedSubgroupTol * scale) {
      cur.push_back(idx);
    } else {
      groups.push_back(cur);
      cur = {idx};
      lam0 = lam;
      scale = std::max(1.0, std::abs(lam0));
    }
  }
  groups.push_back(cur);
  return groups;
}

static Eigen::VectorXd project_coordinate(const Eigen::MatrixXd& M, const Eigen::MatrixXd& V,
                                          int r) {
  Eigen::VectorXd er = Eigen::VectorXd::Zero(V.rows());
  er(r) = 1.0;
  const Eigen::VectorXd mt_er = M * er;
  const Eigen::VectorXd coeffs = V.transpose() * mt_er;
  return V * coeffs;
}

static void mgs_two_pass(Eigen::VectorXd& w, const Eigen::MatrixXd& M,
                         const std::vector<Eigen::VectorXd>& accepted) {
  for (int pass = 0; pass < 2; ++pass) {
    for (const auto& q : accepted) {
      const double overlap = m_inner(M, q, w);
      w -= overlap * q;
    }
  }
}

static void canonicalize_repeated_subgroup(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M,
                                           std::vector<double>& lambdas,
                                           std::vector<Eigen::VectorXd>& vectors,
                                           const std::vector<size_t>& indices) {
  const int k = static_cast<int>(indices.size());
  if (k <= 1) return;

  const int n = static_cast<int>(vectors[indices.front()].size());
  Eigen::MatrixXd V(n, k);
  for (int j = 0; j < k; ++j) V.col(j) = vectors[indices[static_cast<size_t>(j)]];

  std::vector<Eigen::VectorXd> accepted;
  accepted.reserve(static_cast<size_t>(k));
  for (int r = 0; r < n && static_cast<int>(accepted.size()) < k; ++r) {
    Eigen::VectorXd w = project_coordinate(M, V, r);
    mgs_two_pass(w, M, accepted);
    const double norm = m_norm(M, w);
    if (norm <= kProbeNormTol) continue;
    w /= norm;
    fix_sign(w);
    accepted.push_back(std::move(w));
  }
  if (static_cast<int>(accepted.size()) != k) {
    throw std::runtime_error("cannot construct canonical repeated-subspace basis");
  }

  for (int j = 0; j < k; ++j) {
    vectors[indices[static_cast<size_t>(j)]] = accepted[static_cast<size_t>(j)];
    lambdas[indices[static_cast<size_t>(j)]] = rayleigh_quotient(K, M, accepted[static_cast<size_t>(j)]);
  }
}

static void finalize_physical_mode_basis(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M,
                                         std::vector<double>& lambdas,
                                         std::vector<Eigen::VectorXd>& vectors) {
  for (auto& v : vectors) {
    const double n = m_norm(M, v);
    if (n > 1e-30) v /= n;
  }

  const auto cluster_ids = cluster_ids_sorted(lambdas);
  std::vector<int> seen;
  seen.reserve(cluster_ids.size());
  for (int cid : cluster_ids) {
    if (!seen.empty() && seen.back() == cid) continue;
    seen.push_back(cid);
    const auto groups = repeated_subgroups_in_cluster(lambdas, cluster_ids, cid);
    for (const auto& group : groups) {
      if (group.size() > 1) canonicalize_repeated_subgroup(K, M, lambdas, vectors, group);
    }
  }

  for (auto& v : vectors) fix_sign(v);
  for (size_t i = 0; i < vectors.size(); ++i) {
    lambdas[i] = rayleigh_quotient(K, M, vectors[i]);
  }

  struct Item {
    double lambda;
    Eigen::VectorXd vec;
    size_t orig;
  };
  std::vector<Item> items;
  items.reserve(vectors.size());
  for (size_t i = 0; i < vectors.size(); ++i) {
    items.push_back({lambdas[i], vectors[i], i});
  }
  std::stable_sort(items.begin(), items.end(),
                   [](const Item& a, const Item& b) { return a.lambda < b.lambda; });
  for (size_t i = 0; i < items.size(); ++i) {
    lambdas[i] = items[i].lambda;
    vectors[i] = items[i].vec;
  }
}

static void validate_mode_set(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M,
                              const std::vector<double>& lambdas,
                              const std::vector<Eigen::VectorXd>& vectors) {
  if (lambdas.size() != vectors.size()) {
    throw std::runtime_error("checkpoint mode count mismatch");
  }
  for (size_t i = 0; i < vectors.size(); ++i) {
    for (int j = 0; j < vectors[i].size(); ++j) {
      if (!std::isfinite(vectors[i](j))) throw std::runtime_error("non-finite checkpoint vector");
    }
    const double n = m_norm(M, vectors[i]);
    if (std::abs(n - 1.0) > kMOrthonormTol) {
      throw std::runtime_error("checkpoint vector is not M-orthonormal");
    }
    const double rq = rayleigh_quotient(K, M, vectors[i]);
    const double denom = std::max(std::abs(lambdas[i]), 1.0);
    if (std::abs(rq - lambdas[i]) / denom > kRayleighRelTol) {
      throw std::runtime_error("checkpoint Rayleigh quotient mismatch");
    }
  }
  for (size_t i = 0; i < vectors.size(); ++i) {
    for (size_t j = i + 1; j < vectors.size(); ++j) {
      const double overlap = std::abs(m_inner(M, vectors[i], vectors[j]));
      if (overlap > kMOrthonormTol) {
        throw std::runtime_error("checkpoint vectors are not M-orthonormal");
      }
    }
  }
}

}  // namespace

void invalidate_solver_cache() { g_cache = FactorizationCache{}; }

static Eigen::MatrixXd to_dense(const Eigen::SparseMatrix<double>& A) {
  return Eigen::MatrixXd(A);
}

static Eigen::MatrixXd deterministic_initial_subspace(int n, int nmodes) {
  Eigen::MatrixXd Q(n, nmodes);
  for (int i = 0; i < n; ++i) {
    for (int j = 0; j < nmodes; ++j) {
      Q(i, j) = std::sin(0.173 * static_cast<double>((i + 1) * (j + 1)));
    }
  }
  return Q;
}

static void m_orthonormalize(Eigen::MatrixXd& Q, const Eigen::MatrixXd& M) {
  const int m = static_cast<int>(Q.cols());
  for (int j = 0; j < m; ++j) {
    for (int i = 0; i < j; ++i) {
      const double overlap = Q.col(i).dot(M * Q.col(j));
      Q.col(j) -= overlap * Q.col(i);
    }
    const double norm = std::sqrt(std::max(0.0, Q.col(j).dot(M * Q.col(j))));
    if (norm <= 1e-30) throw std::runtime_error("dependent subspace basis");
    Q.col(j) /= norm;
  }
}

static void filter_physical_modes(std::vector<double>& values, std::vector<Eigen::VectorXd>& vectors,
                                  int requested_modes) {
  struct Item {
    double lambda;
    Eigen::VectorXd vec;
  };
  std::vector<Item> items;
  items.reserve(values.size());
  for (size_t i = 0; i < values.size(); ++i) {
    items.push_back({values[i], vectors[i]});
  }
  std::sort(items.begin(), items.end(),
            [](const Item& a, const Item& b) { return a.lambda < b.lambda; });

  double scale = 1.0;
  for (const auto& item : items) {
    scale = std::max(scale, std::abs(item.lambda));
  }
  const double zero_tol = 1e-8 * std::max(1.0, scale);

  values.clear();
  vectors.clear();
  for (const auto& item : items) {
    if (!std::isfinite(item.lambda) || item.lambda <= zero_tol) continue;
    values.push_back(item.lambda);
    vectors.push_back(item.vec);
  }
  if (static_cast<int>(values.size()) < requested_modes) {
    throw std::runtime_error("insufficient physical modes in spectrum");
  }
  values.resize(static_cast<size_t>(requested_modes));
  vectors.resize(static_cast<size_t>(requested_modes));
}

static SolverResult full_generalized_solve(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M,
                                           int nmodes, int iterations, bool converged) {
  Eigen::GeneralizedSelfAdjointEigenSolver<Eigen::MatrixXd> ges(K, M);
  if (ges.info() != Eigen::Success) throw std::runtime_error("generalized eigen solve failed");

  std::vector<double> values;
  std::vector<Eigen::VectorXd> vectors;
  values.reserve(static_cast<size_t>(ges.eigenvalues().size()));
  vectors.reserve(static_cast<size_t>(ges.eigenvalues().size()));
  for (int i = 0; i < ges.eigenvalues().size(); ++i) {
    values.push_back(ges.eigenvalues()(i));
    vectors.push_back(ges.eigenvectors().col(i));
  }
  filter_physical_modes(values, vectors, nmodes);
  finalize_physical_mode_basis(K, M, values, vectors);

  SolverResult res;
  res.iterations = iterations;
  res.converged = converged;
  res.eigenvalues = std::move(values);
  res.eigenvectors = std::move(vectors);
  return res;
}

static SolverResult subspace_iteration(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M,
                                       int nmodes, int max_iter, double tol,
                                       const Eigen::MatrixXd* initial_subspace,
                                       int iter_offset, int checkpoint_after,
                                       CheckpointState* checkpoint_out) {
  const int n = static_cast<int>(K.rows());
  nmodes = std::min(nmodes, n);

  Eigen::MatrixXd Q = initial_subspace ? *initial_subspace : deterministic_initial_subspace(n, nmodes);
  if (Q.cols() != nmodes) Q = deterministic_initial_subspace(n, nmodes);
  m_orthonormalize(Q, M);

  int it = 0;
  bool converged = false;
  Eigen::VectorXd prev(nmodes);
  prev.setZero();

  for (; it < max_iter; ++it) {
    const Eigen::MatrixXd Z = K * Q;
    const Eigen::MatrixXd T = Q.transpose() * K * Q;
    const Eigen::MatrixXd Mr = Q.transpose() * M * Q;
    Eigen::GeneralizedSelfAdjointEigenSolver<Eigen::MatrixXd> ges(T, Mr);
    if (ges.info() != Eigen::Success) throw std::runtime_error("subspace eigen solve failed");

    const Eigen::VectorXd evals = ges.eigenvalues();
    Q = Z * ges.eigenvectors();
    m_orthonormalize(Q, M);

    if (it > 0) {
      converged = true;
      for (int i = 0; i < nmodes; ++i) {
        if (std::abs(evals(i) - prev(i)) > tol) converged = false;
      }
    }
    prev = evals;

    if (checkpoint_out != nullptr && checkpoint_after > 0 && (it + 1) == checkpoint_after) {
      checkpoint_out->iterations = iter_offset + it + 1;
    }

    if (converged) break;
  }

  return full_generalized_solve(K, M, nmodes, iter_offset + it + 1, converged);
}

SolverResult solve_generalized(const Mesh& mesh, const Topology& topo, const OperatorPair& ops,
                               const SolverConfig& cfg) {
  SolverResult result;
  CheckpointState resume_state;
  bool have_resume = false;

  if (cfg.resume) {
    resume_state = read_checkpoint(cfg.resume_path);
    std::string reason;
    if (!checkpoint_compatible(resume_state, mesh, topo, &reason)) {
      throw std::runtime_error("checkpoint incompatible: " + reason);
    }
    have_resume = true;
  }

  const std::string map_tag = topo.fingerprint;
  if (g_cache.valid && g_cache.geometry_hash == mesh.geometry_hash &&
      g_cache.ndof == ops.ndof && g_cache.map_tag == map_tag) {
    /* valid cache */
  } else {
    g_cache.valid = true;
    g_cache.geometry_hash = mesh.geometry_hash;
    g_cache.ndof = ops.ndof;
    g_cache.map_tag = map_tag;
  }

  const Eigen::MatrixXd K = to_dense(ops.K);
  const Eigen::MatrixXd M = to_dense(ops.M);

  if (cfg.checkpoint_path.empty() && !have_resume) {
    return full_generalized_solve(K, M, cfg.requested_modes, 1, true);
  }

  Eigen::MatrixXd initial;
  int iter_offset = 0;
  if (have_resume && !resume_state.ritz_vectors.empty()) {
    const int ndof = ops.ndof;
    const int nmodes = std::min(cfg.requested_modes, static_cast<int>(resume_state.ritz_vectors.size()));
    initial.resize(ndof, nmodes);
    const auto resumed = remap_checkpoint_vectors(resume_state, mesh, topo, ndof);
    validate_mode_set(K, M, resume_state.ritz_values, resumed);

    std::vector<double> remapped_values = resume_state.ritz_values;
    std::vector<Eigen::VectorXd> remapped_vectors = resumed;
    finalize_physical_mode_basis(K, M, remapped_values, remapped_vectors);
    validate_mode_set(K, M, remapped_values, remapped_vectors);

    for (int j = 0; j < nmodes; ++j) initial.col(j) = remapped_vectors[static_cast<size_t>(j)];
    iter_offset = resume_state.iterations;
  }

  CheckpointState partial_ckpt;
  CheckpointState* ckpt_ptr =
      (!cfg.checkpoint_path.empty() && cfg.checkpoint_after > 0) ? &partial_ckpt : nullptr;

  result = subspace_iteration(K, M, cfg.requested_modes, cfg.max_iterations, cfg.tolerance,
                              have_resume ? &initial : nullptr, iter_offset, cfg.checkpoint_after,
                              ckpt_ptr);

  if (ckpt_ptr != nullptr && partial_ckpt.iterations > 0) {
    const SolverResult ckpt_modes =
        full_generalized_solve(K, M, cfg.requested_modes, partial_ckpt.iterations, false);
    const auto ckpt = make_checkpoint_state(mesh, topo, cfg.requested_modes, partial_ckpt.iterations,
                                            ckpt_modes.eigenvalues, ckpt_modes.eigenvectors);
    if (!write_checkpoint(cfg.checkpoint_path, ckpt)) {
      throw std::runtime_error("checkpoint write failed");
    }
  }

  return result;
}

}  // namespace emsolve
