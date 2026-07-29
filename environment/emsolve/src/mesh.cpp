#include "emsolve/mesh.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>

namespace emsolve {

double Vec3::norm() const { return std::sqrt(dot(*this)); }

Vec3 Vec3::normalized() const {
  const double n = norm();
  if (n <= 0.0) return {0, 0, 0};
  return *this * (1.0 / n);
}

static uint64_t fnv1a64(const std::string& s) {
  uint64_t h = 14695981039346656037ULL;
  for (unsigned char c : s) {
    h ^= c;
    h *= 1099511628211ULL;
  }
  return h;
}

void Mesh::compute_geometry_hash() {
  std::ostringstream oss;
  oss.precision(17);
  for (const auto& v : vertices) {
    oss << v.x << ' ' << v.y << ' ' << v.z << '\n';
  }
  geometry_hash = fnv1a64(oss.str());
}

Mesh Mesh::load(const std::string& path) {
  std::ifstream in(path);
  if (!in) throw std::runtime_error("cannot open mesh: " + path);

  Mesh mesh;
  mesh.source_path = path;
  std::string token;
  in >> token;
  if (token != "emsolve-mesh") throw std::runtime_error("invalid mesh header");
  int version = 0;
  in >> version;
  if (version != 1) throw std::runtime_error("unsupported mesh version");

  int nverts = 0;
  in >> token >> nverts;
  if (token != "vertices" || nverts < 4)
    throw std::runtime_error("invalid vertices section");

  mesh.vertices.resize(static_cast<size_t>(nverts));
  std::vector<bool> seen_vertex(static_cast<size_t>(nverts), false);
  for (int i = 0; i < nverts; ++i) {
    int id = 0;
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    in >> id >> x >> y >> z;
    if (id < 0 || id >= nverts) throw std::runtime_error("vertex id out of range");
    if (seen_vertex[static_cast<size_t>(id)]) throw std::runtime_error("duplicate vertex id");
    seen_vertex[static_cast<size_t>(id)] = true;
    mesh.vertices[static_cast<size_t>(id)] = {x, y, z};
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z)) {
      throw std::runtime_error("non-finite vertex coordinate");
    }
  }

  int ntets = 0;
  in >> token >> ntets;
  if (token != "elements" || ntets < 1) throw std::runtime_error("invalid elements section");

  mesh.elements.resize(static_cast<size_t>(ntets));
  std::vector<bool> seen_element(static_cast<size_t>(ntets), false);
  for (int e = 0; e < ntets; ++e) {
    int id = 0;
    int v0 = 0;
    int v1 = 0;
    int v2 = 0;
    int v3 = 0;
    in >> id >> v0 >> v1 >> v2 >> v3;
    if (id < 0 || id >= ntets) throw std::runtime_error("element id out of range");
    if (seen_element[static_cast<size_t>(id)]) throw std::runtime_error("duplicate element id");
    seen_element[static_cast<size_t>(id)] = true;
    mesh.elements[static_cast<size_t>(id)].v[0] = v0;
    mesh.elements[static_cast<size_t>(id)].v[1] = v1;
    mesh.elements[static_cast<size_t>(id)].v[2] = v2;
    mesh.elements[static_cast<size_t>(id)].v[3] = v3;
  }

  int nfaces = 0;
  in >> token >> nfaces;
  if (token != "boundary") throw std::runtime_error("invalid boundary section");

  mesh.boundary_faces.resize(static_cast<size_t>(nfaces));
  std::vector<bool> seen_boundary(static_cast<size_t>(nfaces), false);
  for (int f = 0; f < nfaces; ++f) {
    int id = 0;
    BoundaryFace face;
    in >> id >> face.v[0] >> face.v[1] >> face.v[2] >> face.tag;
    if (id < 0 || id >= nfaces) throw std::runtime_error("boundary id out of range");
    if (seen_boundary[static_cast<size_t>(id)]) throw std::runtime_error("duplicate boundary id");
    seen_boundary[static_cast<size_t>(id)] = true;
    mesh.boundary_faces[static_cast<size_t>(id)] = face;
  }

  std::string trailing;
  if (in >> trailing) throw std::runtime_error("truncated mesh file");

  mesh.validate_or_throw();
  mesh.compute_geometry_hash();
  return mesh;
}

static double tet_volume(const Vec3& a, const Vec3& b, const Vec3& c, const Vec3& d) {
  return std::abs((b - a).cross(c - a).dot(d - a)) / 6.0;
}

void Mesh::validate_or_throw() const {
  if (vertices.size() < 4) throw std::runtime_error("mesh has too few vertices");
  if (elements.empty()) throw std::runtime_error("mesh has no elements");

  for (const auto& t : elements) {
    for (int vid : t.v) {
      if (vid < 0 || vid >= static_cast<int>(vertices.size()))
        throw std::runtime_error("element references invalid vertex");
    }
    const auto& p = vertices;
    const double vol = tet_volume(p[t.v[0]], p[t.v[1]], p[t.v[2]], p[t.v[3]]);
    if (vol <= 1e-14) throw std::runtime_error("degenerate tetrahedron");
  }

  std::unordered_map<std::string, int> face_count;
  std::unordered_set<std::string> element_faces;
  auto face_key = [](int a, int b, int c) {
    std::array<int, 3> v{a, b, c};
    std::sort(v.begin(), v.end());
    return std::to_string(v[0]) + ":" + std::to_string(v[1]) + ":" + std::to_string(v[2]);
  };

  for (const auto& t : elements) {
    const int v[4] = {t.v[0], t.v[1], t.v[2], t.v[3]};
    const int faces[4][3] = {{v[0], v[1], v[2]}, {v[0], v[1], v[3]}, {v[0], v[2], v[3]}, {v[1], v[2], v[3]}};
    for (const auto& f : faces) {
      const std::string key = face_key(f[0], f[1], f[2]);
      face_count[key] += 1;
      element_faces.insert(key);
    }
  }

  for (const auto& kv : face_count) {
    if (kv.second > 2) throw std::runtime_error("nonmanifold face detected");
  }

  for (const auto& face : boundary_faces) {
    for (int vid : face.v) {
      if (vid < 0 || vid >= static_cast<int>(vertices.size()))
        throw std::runtime_error("boundary references invalid vertex");
    }
    if (face.tag != "pec") throw std::runtime_error("unsupported boundary tag: " + face.tag);
    const std::string key = face_key(face.v[0], face.v[1], face.v[2]);
    if (!element_faces.count(key)) throw std::runtime_error("boundary face is not a tetrahedron face");
  }
}

double Mesh::min_edge_length() const {
  double m = 1e100;
  for (const auto& t : elements) {
    for (int i = 0; i < 4; ++i)
      for (int j = i + 1; j < 4; ++j) {
        m = std::min(m, (vertices[t.v[i]] - vertices[t.v[j]]).norm());
      }
  }
  return m;
}

double Mesh::max_edge_length() const {
  double m = 0.0;
  for (const auto& t : elements) {
    for (int i = 0; i < 4; ++i)
      for (int j = i + 1; j < 4; ++j) {
        m = std::max(m, (vertices[t.v[i]] - vertices[t.v[j]]).norm());
      }
  }
  return m;
}

}  // namespace emsolve
