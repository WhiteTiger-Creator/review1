#include "emsolve/topology.hpp"

#include <algorithm>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace emsolve {

namespace {

uint64_t fnv1a64(const std::string& s) {
  uint64_t h = 14695981039346656037ULL;
  for (unsigned char c : s) {
    h ^= c;
    h *= 1099511628211ULL;
  }
  return h;
}

// Strict total order on raw vertex coordinates. Mesh vertices are read
// verbatim (no snapping/quantization) from the mesh file, so two meshes that
// describe the same geometry under different vertex/element numbering carry
// bit-identical coordinate doubles for corresponding points. Comparing on
// coordinates -- rather than on vertex id -- is what makes everything built
// from this ordering (edge identity, edge orientation, edge numbering)
// invariant to renumbering. The vertex-id tiebreak only fires for the
// degenerate case of two mesh vertices sharing an exact coordinate, and only
// exists to keep the order strict/total.
bool less_pos(const Vec3& p, const Vec3& q) {
  if (p.x != q.x) return p.x < q.x;
  if (p.y != q.y) return p.y < q.y;
  if (p.z != q.z) return p.z < q.z;
  return false;
}

// Canonical (lo, hi) endpoint pair for an edge given two global vertex ids,
// ordered by coordinate lexicographic order rather than by numeric id. This
// pair is what defines the "reference direction" (lo -> hi) used everywhere
// downstream (elem_edge_sign, checkpoint edge identity, divergence
// diagnostics), so a given physical edge always has the same reference
// direction no matter which mesh file / numbering it came from.
std::pair<int, int> canonical_endpoints(const Mesh& mesh, int a, int b) {
  const Vec3& pa = mesh.vertices[static_cast<size_t>(a)];
  const Vec3& pb = mesh.vertices[static_cast<size_t>(b)];
  if (less_pos(pb, pa)) return {b, a};
  return {a, b};
}

// Geometry-only key for an edge: the two endpoint coordinates, in
// coordinate-lex order, formatted at full double precision (17 significant
// digits round-trips an IEEE-754 double exactly). This string depends only
// on where the edge's endpoints physically sit in space, never on vertex or
// element numbering, so it is identical across numbering-equivalent meshes.
std::string geom_edge_key(const Vec3& lo, const Vec3& hi) {
  std::ostringstream oss;
  oss.precision(17);
  oss << lo.x << ' ' << lo.y << ' ' << lo.z << '|' << hi.x << ' ' << hi.y << ' ' << hi.z;
  return oss.str();
}

}  // namespace

std::array<int, 6> Topology::local_edge_vertices(int local_idx) {
  static const int table[6][2] = {{0, 1}, {0, 2}, {0, 3}, {1, 2}, {1, 3}, {2, 3}};
  return {table[local_idx][0], table[local_idx][1]};
}

Topology Topology::build(const Mesh& mesh) {
  Topology topo;

  topo.elem_edge_global.resize(mesh.elements.size());
  topo.elem_edge_sign.resize(mesh.elements.size());

  // Pass 1: enumerate every local edge of every element, register it under
  // its geometry-only key, and remember its canonical (lo, hi) endpoints.
  // The temporary id assigned here is just an arbitrary registration order;
  // it gets replaced by a geometry-sorted id in pass 2 below.
  std::unordered_map<std::string, int> key_to_tmp_id;
  std::vector<std::string> tmp_keys;
  std::vector<std::pair<int, int>> tmp_endpoints;

  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    const auto& tet = mesh.elements[e];
    for (int le = 0; le < 6; ++le) {
      const auto lv = local_edge_vertices(le);
      const int va = tet.v[static_cast<size_t>(lv[0])];
      const int vb = tet.v[static_cast<size_t>(lv[1])];
      const auto canon = canonical_endpoints(mesh, va, vb);
      const int lo = canon.first;
      const int hi = canon.second;
      const std::string key =
          geom_edge_key(mesh.vertices[static_cast<size_t>(lo)], mesh.vertices[static_cast<size_t>(hi)]);

      int tmp_id;
      auto it = key_to_tmp_id.find(key);
      if (it != key_to_tmp_id.end()) {
        tmp_id = it->second;
      } else {
        tmp_id = static_cast<int>(tmp_keys.size());
        key_to_tmp_id.emplace(key, tmp_id);
        tmp_keys.push_back(key);
        tmp_endpoints.emplace_back(lo, hi);
      }

      topo.elem_edge_global[e][static_cast<size_t>(le)] = tmp_id;
      // Sign is defined purely from the canonical (geometry-based)
      // orientation: +1 if this element visits the edge lo->hi, -1 if it
      // visits it hi->lo. This is invariant to element order and to the
      // local vertex table used by any particular element.
      topo.elem_edge_sign[e][static_cast<size_t>(le)] = (va == lo && vb == hi) ? 1 : -1;
    }
  }

  // Pass 2: assign the *final* global edge numbering by sorting the
  // geometry-only keys. This is the crux of "geometry-canonical" topology:
  // the resulting edge ids -- and therefore every reduced dof index built
  // from them -- are a pure function of the mesh's geometry, not of the
  // order vertices/elements happen to appear in the file.
  const int n_edges = static_cast<int>(tmp_keys.size());
  std::vector<int> order(static_cast<size_t>(n_edges));
  for (int i = 0; i < n_edges; ++i) order[static_cast<size_t>(i)] = i;
  std::sort(order.begin(), order.end(),
            [&](int a, int b) { return tmp_keys[static_cast<size_t>(a)] < tmp_keys[static_cast<size_t>(b)]; });

  std::vector<int> tmp_to_final(static_cast<size_t>(n_edges));
  for (int final_id = 0; final_id < n_edges; ++final_id) {
    tmp_to_final[static_cast<size_t>(order[static_cast<size_t>(final_id)])] = final_id;
  }

  topo.edges.resize(static_cast<size_t>(n_edges));
  for (int tmp_id = 0; tmp_id < n_edges; ++tmp_id) {
    const int final_id = tmp_to_final[static_cast<size_t>(tmp_id)];
    GlobalEdge ge;
    ge.v0 = tmp_endpoints[static_cast<size_t>(tmp_id)].first;   // canonical "lo"
    ge.v1 = tmp_endpoints[static_cast<size_t>(tmp_id)].second;  // canonical "hi"
    topo.edges[static_cast<size_t>(final_id)] = ge;
  }
  topo.num_global_edges = n_edges;

  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    for (int le = 0; le < 6; ++le) {
      int& gid = topo.elem_edge_global[e][static_cast<size_t>(le)];
      gid = tmp_to_final[static_cast<size_t>(gid)];
    }
  }

  // PEC boundary elimination: identify boundary edges through the same
  // geometry-canonical key used for interior/element edges, so elimination
  // is independent of boundary-face vertex order and numbering.
  std::unordered_set<int> boundary_edge_set;
  for (const auto& face : mesh.boundary_faces) {
    if (face.tag != "pec") continue;
    const int fv[3] = {face.v[0], face.v[1], face.v[2]};
    const int pairs[3][2] = {{fv[0], fv[1]}, {fv[1], fv[2]}, {fv[0], fv[2]}};
    for (const auto& pr : pairs) {
      const auto canon = canonical_endpoints(mesh, pr[0], pr[1]);
      const std::string key = geom_edge_key(mesh.vertices[static_cast<size_t>(canon.first)],
                                            mesh.vertices[static_cast<size_t>(canon.second)]);
      auto it = key_to_tmp_id.find(key);
      if (it == key_to_tmp_id.end()) {
        throw std::runtime_error("pec boundary edge does not match any element edge");
      }
      boundary_edge_set.insert(tmp_to_final[static_cast<size_t>(it->second)]);
    }
  }

  topo.boundary_edges.assign(boundary_edge_set.begin(), boundary_edge_set.end());
  std::sort(topo.boundary_edges.begin(), topo.boundary_edges.end());

  std::vector<int> active;
  active.reserve(static_cast<size_t>(topo.num_global_edges));
  for (int i = 0; i < topo.num_global_edges; ++i) {
    if (!boundary_edge_set.count(i)) active.push_back(i);
  }
  // `active` is already strictly increasing: global edge ids are assigned
  // in sorted geometric-key order (pass 2 above) and removing a subset
  // preserves relative order.

  topo.num_active_dofs = static_cast<int>(active.size());
  topo.global_to_reduced.assign(static_cast<size_t>(topo.num_global_edges), -1);
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    topo.global_to_reduced[static_cast<size_t>(active[static_cast<size_t>(r)])] = r;
  }

  // Single, unified reduced<->global map for both operators. K and M MUST
  // index degrees of freedom identically -- if they used different maps
  // (e.g. one sorted, one in mesh-file insertion order), K x = lambda M x
  // would silently mix up which row of K corresponds to which row of M,
  // producing physically wrong eigenpairs that depend on mesh/element
  // numbering even though the underlying geometry is unchanged.
  topo.reduced_to_global_k = active;
  topo.reduced_to_global_m = active;

  std::ostringstream fp;
  fp << "edges=" << topo.num_global_edges << "|active=" << topo.num_active_dofs << "|keys=";
  for (const int tmp_id : order) fp << tmp_keys[static_cast<size_t>(tmp_id)] << ';';
  topo.fingerprint = std::to_string(fnv1a64(fp.str()));

  return topo;
}

}  // namespace emsolve
