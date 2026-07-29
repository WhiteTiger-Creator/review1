#include "emsolve/assembly.hpp"

#include <array>
#include <cmath>
#include <vector>

namespace emsolve {

static void local_nedelec_matrices(const Vec3 p[4], Eigen::Matrix<double, 6, 6>& Kloc,
                                   Eigen::Matrix<double, 6, 6>& Mloc) {
  static const int edges[6][2] = {{0, 1}, {0, 2}, {0, 3}, {1, 2}, {1, 3}, {2, 3}};

  const double vol = std::abs((p[1] - p[0]).cross(p[2] - p[0]).dot(p[3] - p[0])) / 6.0;
  const double inv_vol = 1.0 / std::max(vol, 1e-30);

  Kloc.setZero();
  Mloc.setZero();

  std::array<Vec3, 6> ev{};
  for (int i = 0; i < 6; ++i) {
    const int a = edges[i][0];
    const int b = edges[i][1];
    ev[static_cast<size_t>(i)] = p[b] - p[a];
  }

  for (int i = 0; i < 6; ++i) {
    for (int j = 0; j < 6; ++j) {
      const double mij = ev[static_cast<size_t>(i)].dot(ev[static_cast<size_t>(j)]) * vol / 12.0;
      Mloc(i, j) = (i == j) ? 2.0 * mij : mij;
      Kloc(i, j) = ev[static_cast<size_t>(i)].dot(ev[static_cast<size_t>(j)]) * inv_vol;
    }
  }
}

static void add_local(Eigen::SparseMatrix<double>& K, Eigen::SparseMatrix<double>& M,
                      const Eigen::Matrix<double, 6, 6>& Kloc,
                      const Eigen::Matrix<double, 6, 6>& Mloc, const std::array<int, 6>& gids,
                      const std::array<int, 6>& signs, const std::vector<int>& red_k,
                      const std::vector<int>& red_m) {
  std::array<int, 6> rk{};
  std::array<int, 6> rm{};
  for (int i = 0; i < 6; ++i) {
    rk[static_cast<size_t>(i)] = red_k[static_cast<size_t>(gids[static_cast<size_t>(i)])];
    rm[static_cast<size_t>(i)] = red_m[static_cast<size_t>(gids[static_cast<size_t>(i)])];
  }

  for (int i = 0; i < 6; ++i) {
    if (rk[static_cast<size_t>(i)] < 0) continue;
    for (int j = 0; j < 6; ++j) {
      if (rk[static_cast<size_t>(j)] < 0) continue;
      const double sK = signs[static_cast<size_t>(i)] * signs[static_cast<size_t>(j)];
      K.coeffRef(rk[static_cast<size_t>(i)], rk[static_cast<size_t>(j)]) += sK * Kloc(i, j);
    }
  }

  for (int i = 0; i < 6; ++i) {
    if (rm[static_cast<size_t>(i)] < 0) continue;
    for (int j = 0; j < 6; ++j) {
      if (rm[static_cast<size_t>(j)] < 0) continue;
      const double sM = signs[static_cast<size_t>(i)] * signs[static_cast<size_t>(j)];
      M.coeffRef(rm[static_cast<size_t>(i)], rm[static_cast<size_t>(j)]) += sM * Mloc(i, j);
    }
  }
}

OperatorPair assemble_operators(const Mesh& mesh, const Topology& topo) {
  OperatorPair ops;
  ops.ndof = topo.num_active_dofs;
  ops.K.resize(ops.ndof, ops.ndof);
  ops.M.resize(ops.ndof, ops.ndof);

  std::vector<int> red_k(topo.num_global_edges, -1);
  std::vector<int> red_m(topo.num_global_edges, -1);
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    red_k[static_cast<size_t>(topo.reduced_to_global_k[static_cast<size_t>(r)])] = r;
    red_m[static_cast<size_t>(topo.reduced_to_global_m[static_cast<size_t>(r)])] = r;
  }

  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    const auto& tet = mesh.elements[e];
    Vec3 p[4];
    for (int i = 0; i < 4; ++i) p[i] = mesh.vertices[tet.v[i]];

    Eigen::Matrix<double, 6, 6> Kloc, Mloc;
    local_nedelec_matrices(p, Kloc, Mloc);
    add_local(ops.K, ops.M, Kloc, Mloc, topo.elem_edge_global[e], topo.elem_edge_sign[e], red_k,
              red_m);
  }

  ops.K.makeCompressed();
  ops.M.makeCompressed();
  return ops;
}

std::vector<double> reconstruct_edge_field(const Mesh& mesh, const Topology& topo,
                                           const Eigen::VectorXd& x_reduced, bool use_k_map) {
  const auto& r2g = use_k_map ? topo.reduced_to_global_k : topo.reduced_to_global_m;
  std::vector<double> global(static_cast<size_t>(topo.num_global_edges), 0.0);
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    global[static_cast<size_t>(r2g[static_cast<size_t>(r)])] = x_reduced(r);
  }

  std::vector<double> samples;
  samples.reserve(mesh.elements.size() * 6);
  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    for (int le = 0; le < 6; ++le) {
      const int gid = topo.elem_edge_global[e][static_cast<size_t>(le)];
      double val = global[static_cast<size_t>(gid)];
      samples.push_back(val * topo.elem_edge_sign[e][static_cast<size_t>(le)]);
    }
  }
  return samples;
}

}  // namespace emsolve
