#include "emsolve/assembly.hpp"

#include <array>
#include <cmath>
#include <vector>

#include <Eigen/Dense>

namespace emsolve {

namespace {

struct TetGeometry {
  Vec3 grad[4];
  double volume{0.0};
};

static TetGeometry barycentric_gradients(const Vec3 p[4]) {
  TetGeometry g;
  const Vec3 r1 = p[1] - p[0];
  const Vec3 r2 = p[2] - p[0];
  const Vec3 r3 = p[3] - p[0];

  Eigen::Matrix3d mat;
  mat.col(0) = Eigen::Vector3d(r1.x, r1.y, r1.z);
  mat.col(1) = Eigen::Vector3d(r2.x, r2.y, r2.z);
  mat.col(2) = Eigen::Vector3d(r3.x, r3.y, r3.z);

  const double det = mat.determinant();
  g.volume = std::abs(det) / 6.0;
  if (g.volume <= 1e-14) throw std::runtime_error("degenerate tetrahedron");

  const Eigen::Matrix3d minv = mat.inverse();
  g.grad[1] = Vec3(minv(0, 0), minv(0, 1), minv(0, 2));
  g.grad[2] = Vec3(minv(1, 0), minv(1, 1), minv(1, 2));
  g.grad[3] = Vec3(minv(2, 0), minv(2, 1), minv(2, 2));
  g.grad[0] = (g.grad[1] + g.grad[2] + g.grad[3]) * -1.0;
  return g;
}

static void local_nedelec_matrices(const Vec3 p[4], Eigen::Matrix<double, 6, 6>& Kloc,
                                   Eigen::Matrix<double, 6, 6>& Mloc) {
  static const int edges[6][2] = {{0, 1}, {0, 2}, {0, 3}, {1, 2}, {1, 3}, {2, 3}};
  static const double alpha = (5.0 + 3.0 * std::sqrt(5.0)) / 20.0;
  static const double beta = (5.0 - std::sqrt(5.0)) / 20.0;
  static const double quad_pts[4][4] = {
      {alpha, beta, beta, beta},
      {beta, alpha, beta, beta},
      {beta, beta, alpha, beta},
      {beta, beta, beta, alpha},
  };
  static const double quad_w = 0.25;

  const TetGeometry geom = barycentric_gradients(p);
  Kloc.setZero();
  Mloc.setZero();

  std::array<Vec3, 6> curls{};
  for (int a = 0; a < 6; ++a) {
    const int i = edges[a][0];
    const int j = edges[a][1];
    curls[static_cast<size_t>(a)] = geom.grad[i].cross(geom.grad[j]) * 2.0;
  }

  for (int a = 0; a < 6; ++a) {
    for (int b = 0; b < 6; ++b) {
      Kloc(a, b) = geom.volume * curls[static_cast<size_t>(a)].dot(curls[static_cast<size_t>(b)]);
    }
  }

  for (int q = 0; q < 4; ++q) {
    const double w = quad_w * geom.volume;
    std::array<Vec3, 6> basis{};
    for (int a = 0; a < 6; ++a) {
      const int i = edges[a][0];
      const int j = edges[a][1];
      const double li = quad_pts[q][i];
      const double lj = quad_pts[q][j];
      basis[static_cast<size_t>(a)] =
          geom.grad[j] * li - geom.grad[i] * lj;
    }
    for (int a = 0; a < 6; ++a) {
      for (int b = 0; b < 6; ++b) {
        Mloc(a, b) += w * basis[static_cast<size_t>(a)].dot(basis[static_cast<size_t>(b)]);
      }
    }
  }
}

static void add_local(Eigen::SparseMatrix<double>& K, Eigen::SparseMatrix<double>& M,
                      const Eigen::Matrix<double, 6, 6>& Kloc,
                      const Eigen::Matrix<double, 6, 6>& Mloc, const std::array<int, 6>& gids,
                      const std::array<int, 6>& signs, const std::vector<int>& red) {
  std::array<int, 6> r{};
  for (int i = 0; i < 6; ++i) {
    r[static_cast<size_t>(i)] = red[static_cast<size_t>(gids[static_cast<size_t>(i)])];
  }

  for (int i = 0; i < 6; ++i) {
    if (r[static_cast<size_t>(i)] < 0) continue;
    for (int j = 0; j < 6; ++j) {
      if (r[static_cast<size_t>(j)] < 0) continue;
      const double s = signs[static_cast<size_t>(i)] * signs[static_cast<size_t>(j)];
      K.coeffRef(r[static_cast<size_t>(i)], r[static_cast<size_t>(j)]) += s * Kloc(i, j);
      M.coeffRef(r[static_cast<size_t>(i)], r[static_cast<size_t>(j)]) += s * Mloc(i, j);
    }
  }
}

}  // namespace

OperatorPair assemble_operators(const Mesh& mesh, const Topology& topo) {
  OperatorPair ops;
  ops.ndof = topo.num_active_dofs;
  ops.K.resize(ops.ndof, ops.ndof);
  ops.M.resize(ops.ndof, ops.ndof);

  std::vector<int> red(static_cast<size_t>(topo.num_global_edges), -1);
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    red[static_cast<size_t>(topo.reduced_to_global_k[static_cast<size_t>(r)])] = r;
  }

  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    const auto& tet = mesh.elements[e];
    Vec3 p[4];
    for (int i = 0; i < 4; ++i) p[i] = mesh.vertices[static_cast<size_t>(tet.v[i])];

    Eigen::Matrix<double, 6, 6> Kloc, Mloc;
    local_nedelec_matrices(p, Kloc, Mloc);
    add_local(ops.K, ops.M, Kloc, Mloc, topo.elem_edge_global[e], topo.elem_edge_sign[e], red);
  }

  ops.K.makeCompressed();
  ops.M.makeCompressed();
  return ops;
}

std::vector<double> reconstruct_edge_field(const Mesh& mesh, const Topology& topo,
                                           const Eigen::VectorXd& x_reduced, bool use_k_map) {
  (void)use_k_map;
  const auto& r2g = topo.reduced_to_global_k;
  std::vector<double> global(static_cast<size_t>(topo.num_global_edges), 0.0);
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    global[static_cast<size_t>(r2g[static_cast<size_t>(r)])] = x_reduced(r);
  }

  std::vector<double> samples;
  samples.reserve(mesh.elements.size() * 6);
  for (size_t e = 0; e < mesh.elements.size(); ++e) {
    for (int le = 0; le < 6; ++le) {
      const int gid = topo.elem_edge_global[e][static_cast<size_t>(le)];
      const double val = global[static_cast<size_t>(gid)];
      samples.push_back(val * topo.elem_edge_sign[e][static_cast<size_t>(le)]);
    }
  }
  return samples;
}

}  // namespace emsolve
