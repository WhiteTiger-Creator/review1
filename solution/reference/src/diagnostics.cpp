#include "emsolve/diagnostics.hpp"

#include <cmath>
#include <vector>

#include "emsolve/assembly.hpp"

namespace emsolve {

namespace {

static double algebraic_residual(const OperatorPair& ops, double lambda, const Eigen::VectorXd& x) {
  const Eigen::VectorXd r = ops.K * x - lambda * (ops.M * x);
  return r.norm() / std::max(1.0, x.norm());
}

static double boundary_trace_residual(const Mesh& mesh, const Topology& topo,
                                      const Eigen::VectorXd& x) {
  (void)mesh;
  double sum = 0.0;
  int count = 0;
  std::vector<double> global(static_cast<size_t>(topo.num_global_edges), 0.0);
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    global[static_cast<size_t>(topo.reduced_to_global_k[static_cast<size_t>(r)])] = x(r);
  }
  for (int gid : topo.boundary_edges) {
    sum += global[static_cast<size_t>(gid)] * global[static_cast<size_t>(gid)];
    ++count;
  }
  if (count == 0) return 0.0;
  return std::sqrt(sum / count);
}

static double divergence_residual(const Mesh& mesh, const Topology& topo, const Eigen::VectorXd& x) {
  (void)mesh;
  std::vector<double> global_k(static_cast<size_t>(topo.num_global_edges), 0.0);
  std::vector<double> global_m(static_cast<size_t>(topo.num_global_edges), 0.0);
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    global_k[static_cast<size_t>(topo.reduced_to_global_k[static_cast<size_t>(r)])] = x(r);
    global_m[static_cast<size_t>(topo.reduced_to_global_m[static_cast<size_t>(r)])] = x(r);
  }

  double sum = 0.0;
  int count = 0;
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    const int gk = topo.reduced_to_global_k[static_cast<size_t>(r)];
    const int gm = topo.reduced_to_global_m[static_cast<size_t>(r)];
    const double d = global_k[static_cast<size_t>(gk)] - global_m[static_cast<size_t>(gm)];
    sum += d * d;
    ++count;
  }
  if (count == 0) return 0.0;
  return std::sqrt(sum / count);
}

}  // namespace

ModeDiagnostics compute_mode_diagnostics(const Mesh& mesh, const Topology& topo,
                                         const OperatorPair& ops, double lambda,
                                         const Eigen::VectorXd& x) {
  ModeDiagnostics d;
  d.algebraic_residual = algebraic_residual(ops, lambda, x);
  d.boundary_trace = boundary_trace_residual(mesh, topo, x);
  d.divergence = divergence_residual(mesh, topo, x);
  return d;
}

std::vector<ModeDiagnostics> compute_all_diagnostics(
    const Mesh& mesh, const Topology& topo, const OperatorPair& ops,
    const std::vector<double>& lambdas, const std::vector<Eigen::VectorXd>& vectors) {
  std::vector<ModeDiagnostics> out;
  out.reserve(lambdas.size());
  for (size_t i = 0; i < lambdas.size(); ++i) {
    out.push_back(compute_mode_diagnostics(mesh, topo, ops, lambdas[i], vectors[i]));
  }
  return out;
}

}  // namespace emsolve
