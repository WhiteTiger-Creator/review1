#pragma once

#include <Eigen/Sparse>
#include <string>
#include <vector>

#include "emsolve/assembly.hpp"
#include "emsolve/mesh.hpp"
#include "emsolve/topology.hpp"

namespace emsolve {

struct SolverConfig {
  int max_iterations{200};
  int requested_modes{4};
  double tolerance{1e-10};
  int checkpoint_after{0};
  std::string checkpoint_path;
  bool resume{false};
  std::string resume_path;
};

struct SolverResult {
  std::vector<double> eigenvalues;
  std::vector<Eigen::VectorXd> eigenvectors;
  std::vector<int> cluster_ids;
  int iterations{0};
  bool converged{false};
};

struct FactorizationCache {
  bool valid{false};
  uint64_t geometry_hash{0};
  int ndof{0};
  std::string map_tag;
};

SolverResult solve_generalized(const Mesh& mesh, const Topology& topo, const OperatorPair& ops,
                               const SolverConfig& cfg);

void invalidate_solver_cache();

}  // namespace emsolve
