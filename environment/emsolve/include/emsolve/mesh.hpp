#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace emsolve {

struct Vec3 {
  double x{0}, y{0}, z{0};
  Vec3() = default;
  Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}
  Vec3 operator+(const Vec3& o) const { return {x + o.x, y + o.y, z + o.z}; }
  Vec3 operator-(const Vec3& o) const { return {x - o.x, y - o.y, z - o.z}; }
  Vec3 operator*(double s) const { return {x * s, y * s, z * s}; }
  double dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
  Vec3 cross(const Vec3& o) const {
    return {y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x};
  }
  double norm() const;
  Vec3 normalized() const;
};

struct Tetrahedron {
  std::array<int, 4> v{};
};

struct BoundaryFace {
  std::array<int, 3> v{};
  std::string tag;
};

struct Mesh {
  std::vector<Vec3> vertices;
  std::vector<Tetrahedron> elements;
  std::vector<BoundaryFace> boundary_faces;
  std::string source_path;
  uint64_t geometry_hash{0};

  static Mesh load(const std::string& path);
  void validate_or_throw() const;
  void compute_geometry_hash();
  double min_edge_length() const;
  double max_edge_length() const;
};

}  // namespace emsolve
