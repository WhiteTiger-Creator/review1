#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "emsolve/mesh.hpp"

namespace emsolve {

struct GlobalEdge {
  int v0{0};
  int v1{0};
};

struct Topology {
  std::vector<GlobalEdge> edges;
  std::vector<std::array<int, 6>> elem_edge_global;
  std::vector<std::array<int, 6>> elem_edge_sign;
  std::vector<int> boundary_edges;
  std::vector<int> reduced_to_global_k;
  std::vector<int> reduced_to_global_m;
  std::vector<int> global_to_reduced;
  int num_global_edges{0};
  int num_active_dofs{0};
  std::string fingerprint;

  static Topology build(const Mesh& mesh);
  static std::array<int, 6> local_edge_vertices(int local_idx);
};

}  // namespace emsolve
