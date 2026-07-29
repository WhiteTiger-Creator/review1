#include "emsolve/eigensolver.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>

#include <Eigen/Eigenvalues>

#include "emsolve/checkpoint.hpp"

namespace emsolve {

static FactorizationCache g_cache;

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
    for (int j = 0; j < nmodes; ++j) initial.col(j) = resumed[static_cast<size_t>(j)];
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
