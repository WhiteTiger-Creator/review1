#include "emsolve/topology.hpp"

#include <algorithm>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

namespace emsolve {

static uint64_t fnv1a64(const std::string& s) {
  uint64_t h = 14695981039346656037ULL;
  for (unsigned char c : s) {
    h ^= c;
    h *= 1099511628211ULL;
  }
  return h;
}

std::array<int, 6> Topology::local_edge_vertices(int local_idx) {
  static const int table[6][2] = {{0, 1}, {0, 2}, {0, 3}, {1, 2}, {1, 3}, {2, 3}};
  return {table[local_idx][0], table[local_idx][1]};
}

Topology Topology::build(const Mesh& mesh) {
  Topology topo;
  std::unordered_map<std::string, int> edge_map;
  auto edge_key = [](int a, int b) {
    if (a > b) std::swap(a, b);
    return std::to_string(a) + ":" + std::to_string(b);
  };

  auto get_global_edge = [&](int a, int b) {
    const std::string key = edge_key(a, b);
    auto it = edge_map.find(key);
    if (it != edge_map.end()) return it->second;
    const int id = static_cast<int>(topo.edges.size());
    GlobalEdge e;
    e.v0 = std::min(a, b);
    e.v1 = std::max(a, b);
    topo.edges.push_back(e);
    edge_map[key] = id;
    return id;
  };

  topo.elem_edge_global.resize(mesh.elements.size());
  topo.elem_edge_sign.resize(mesh.elements.size());

  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    const auto& tet = mesh.elements[e];
    for (int le = 0; le < 6; ++le) {
      const auto lv = local_edge_vertices(le);
      const int ga = tet.v[lv[0]];
      const int gb = tet.v[lv[1]];
      const int gid = get_global_edge(ga, gb);
      topo.elem_edge_global[e][static_cast<size_t>(le)] = gid;
      const GlobalEdge& ge = topo.edges[static_cast<size_t>(gid)];
      const int sign = (ga == ge.v0 && gb == ge.v1) ? 1 : -1;
      topo.elem_edge_sign[e][static_cast<size_t>(le)] = sign;
    }
  }

  topo.num_global_edges = static_cast<int>(topo.edges.size());
  std::unordered_set<int> boundary_edge_set;

  for (const auto& face : mesh.boundary_faces) {
    if (face.tag != "pec") continue;
    const int fv[3] = {face.v[0], face.v[1], face.v[2]};
    const int pairs[3][2] = {{fv[0], fv[1]}, {fv[1], fv[2]}, {fv[0], fv[2]}};
    for (const auto& pr : pairs) {
      const int gid = get_global_edge(pr[0], pr[1]);
      boundary_edge_set.insert(gid);
    }
  }

  topo.boundary_edges.assign(boundary_edge_set.begin(), boundary_edge_set.end());
  std::sort(topo.boundary_edges.begin(), topo.boundary_edges.end());

  std::vector<int> active;
  for (int i = 0; i < topo.num_global_edges; ++i) {
    if (!boundary_edge_set.count(i)) active.push_back(i);
  }

  topo.num_active_dofs = static_cast<int>(active.size());
  topo.global_to_reduced.assign(topo.num_global_edges, -1);

  topo.reduced_to_global_k = active;
  std::sort(topo.reduced_to_global_k.begin(), topo.reduced_to_global_k.end());
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    topo.global_to_reduced[topo.reduced_to_global_k[static_cast<size_t>(r)]] = r;
  }

  std::vector<int> insertion_order;
  std::unordered_set<int> seen;
  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    for (int le = 0; le < 6; ++le) {
      const int gid = topo.elem_edge_global[e][static_cast<size_t>(le)];
      if (boundary_edge_set.count(gid) || seen.count(gid)) continue;
      seen.insert(gid);
      insertion_order.push_back(gid);
    }
  }
  topo.reduced_to_global_m = insertion_order;

  std::ostringstream fp;
  fp << "edges=" << topo.num_global_edges << "|active=" << topo.num_active_dofs
     << "|geom=" << mesh.geometry_hash;
  topo.fingerprint = std::to_string(fnv1a64(fp.str()));
  return topo;
}

}  // namespace emsolve
