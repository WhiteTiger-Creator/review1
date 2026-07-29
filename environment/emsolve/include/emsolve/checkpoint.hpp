#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include <Eigen/Dense>

#include "emsolve/mesh.hpp"
#include "emsolve/topology.hpp"

namespace emsolve {

// Checkpoint format version 3 (see /app/docs/checkpoint-format.md).
struct CheckpointState {
  uint32_t version{3};
  int requested_modes{0};
  int iterations{0};
  int active_dofs{0};
  uint64_t lineage_digest{0};
  std::vector<double> edge_identities;
  std::vector<double> ritz_values;
  std::vector<Eigen::VectorXd> ritz_vectors;
  std::string cache_tag;
};

bool write_checkpoint(const std::string& path, const CheckpointState& state);
CheckpointState read_checkpoint(const std::string& path);
bool checkpoint_compatible(const CheckpointState& ckpt, const Mesh& mesh, const Topology& topo,
                           std::string* reason);

CheckpointState make_checkpoint_state(const Mesh& mesh, const Topology& topo, int requested_modes,
                                    int iterations, const std::vector<double>& values,
                                    const std::vector<Eigen::VectorXd>& vectors);

std::vector<Eigen::VectorXd> remap_checkpoint_vectors(const CheckpointState& ckpt, const Mesh& mesh,
                                                      const Topology& topo, int ndof);

}  // namespace emsolve
