#pragma once

#include <vector>

#include <Eigen/Dense>

#include "emsolve/diagnostics.hpp"

namespace emsolve {

struct ModeRecord {
  int index{0};
  double eigenvalue{0.0};
  std::vector<double> coefficients;
  ModeDiagnostics diagnostics;
  int cluster_id{0};
};

struct ModesOutput {
  int requested{0};
  int computed{0};
  std::vector<ModeRecord> modes;
  std::string mesh_path;
  int active_dofs{0};
  int iterations{0};
};

ModesOutput prepare_modes(int requested, const std::vector<double>& lambdas,
                          const std::vector<Eigen::VectorXd>& vectors,
                          const std::vector<ModeDiagnostics>& diags,
                          const std::vector<int>* cluster_ids = nullptr);

}  // namespace emsolve
