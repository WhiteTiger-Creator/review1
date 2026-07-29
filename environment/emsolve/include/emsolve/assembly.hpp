#pragma once

#include <Eigen/Sparse>

#include "emsolve/mesh.hpp"
#include "emsolve/topology.hpp"

namespace emsolve {

struct OperatorPair {
  Eigen::SparseMatrix<double> K;
  Eigen::SparseMatrix<double> M;
  int ndof{0};
};

OperatorPair assemble_operators(const Mesh& mesh, const Topology& topo);

std::vector<double> reconstruct_edge_field(const Mesh& mesh, const Topology& topo,
                                           const Eigen::VectorXd& x_reduced,
                                           bool use_k_map);

}  // namespace emsolve
