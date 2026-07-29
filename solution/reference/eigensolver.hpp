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

void finalize_physical_modes(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M, int requested_modes,
                             std::vector<double>& eigenvalues,
                             std::vector<Eigen::VectorXd>& eigenvectors);

void validate_physical_mode_basis(const Eigen::MatrixXd& K, const Eigen::MatrixXd& M,
                                  const std::vector<double>& eigenvalues,
                                  const std::vector<Eigen::VectorXd>& eigenvectors);

}  // namespace emsolve
