#pragma once

#include <Eigen/Sparse>
#include <vector>

#include "emsolve/assembly.hpp"
#include "emsolve/mesh.hpp"
#include "emsolve/topology.hpp"

namespace emsolve {

struct ModeDiagnostics {
  double algebraic_residual{0.0};
  double boundary_trace{0.0};
  double divergence{0.0};
};

ModeDiagnostics compute_mode_diagnostics(const Mesh& mesh, const Topology& topo,
                                         const OperatorPair& ops, double lambda,
                                         const Eigen::VectorXd& x_reduced);

std::vector<ModeDiagnostics> compute_all_diagnostics(
    const Mesh& mesh, const Topology& topo, const OperatorPair& ops,
    const std::vector<double>& lambdas, const std::vector<Eigen::VectorXd>& vectors);

}  // namespace emsolve
