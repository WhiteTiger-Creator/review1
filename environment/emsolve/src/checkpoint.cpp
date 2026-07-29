#include "emsolve/checkpoint.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

namespace emsolve {

namespace {

constexpr char kMagic[4] = {'E', 'M', 'C', 'K'};
constexpr uint32_t kVersion = 3;

uint64_t fnv1a64(const std::string& s) {
  uint64_t h = 14695981039346656037ULL;
  for (unsigned char c : s) {
    h ^= c;
    h *= 1099511628211ULL;
  }
  return h;
}

uint64_t fnv1a64_bytes(const std::string& bytes) { return fnv1a64(bytes); }

void write_pod(std::ostream& out, const void* data, std::size_t nbytes) {
  out.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(nbytes));
  if (!out) throw std::runtime_error("checkpoint write failed");
}

void read_pod(std::istream& in, void* data, std::size_t nbytes) {
  in.read(reinterpret_cast<char*>(data), static_cast<std::streamsize>(nbytes));
  if (!in) throw std::runtime_error("checkpoint read failed");
}

bool less_pos(const Vec3& p, const Vec3& q) {
  if (p.x != q.x) return p.x < q.x;
  if (p.y != q.y) return p.y < q.y;
  return p.z < q.z;
}

std::string canonical_edge_key(const Mesh& mesh, const Topology& topo, int reduced_idx) {
  const int gid = topo.reduced_to_global_k[static_cast<size_t>(reduced_idx)];
  const GlobalEdge& ge = topo.edges[static_cast<size_t>(gid)];
  Vec3 a = mesh.vertices[static_cast<size_t>(ge.v0)];
  Vec3 b = mesh.vertices[static_cast<size_t>(ge.v1)];
  if (less_pos(b, a)) std::swap(a, b);
  std::ostringstream oss;
  oss.precision(17);
  oss << a.x << ' ' << a.y << ' ' << a.z << '|' << b.x << ' ' << b.y << ' ' << b.z;
  return oss.str();
}

double edge_identity_value(const std::string& key) {
  const uint64_t h = fnv1a64(key);
  double out = 0.0;
  std::memcpy(&out, &h, sizeof(out));
  return out;
}

std::vector<double> live_edge_identities(const Mesh& mesh, const Topology& topo) {
  std::vector<double> ids;
  ids.reserve(static_cast<size_t>(topo.num_active_dofs));
  for (int r = 0; r < topo.num_active_dofs; ++r) {
    ids.push_back(edge_identity_value(canonical_edge_key(mesh, topo, r)));
  }
  return ids;
}

uint64_t lineage_digest_from_identities(const std::vector<double>& ids) {
  std::string bytes;
  bytes.resize(ids.size() * sizeof(double));
  if (!ids.empty()) std::memcpy(bytes.data(), ids.data(), bytes.size());
  return fnv1a64_bytes(bytes);
}

bool identities_strictly_valid(const std::vector<double>& ids) {
  if (ids.empty()) return false;
  std::unordered_map<uint64_t, int> seen;
  for (double d : ids) {
    if (!std::isfinite(d)) return false;
    uint64_t bits = 0;
    std::memcpy(&bits, &d, sizeof(bits));
    if (seen.count(bits)) return false;
    seen[bits] = 1;
  }
  return true;
}

double ritz_zero_tolerance(const std::vector<double>& values) {
  double scale = 1.0;
  for (double v : values) {
    if (std::isfinite(v)) scale = std::max(scale, std::abs(v));
  }
  return 1e-8 * std::max(1.0, scale);
}

bool ritz_values_strictly_valid(const std::vector<double>& values) {
  if (values.empty()) return false;
  const double zero_tol = ritz_zero_tolerance(values);
  for (double v : values) {
    if (!std::isfinite(v) || v <= zero_tol) return false;
  }
  for (std::size_t i = 1; i < values.size(); ++i) {
    if (values[i] < values[i - 1]) return false;
  }
  return true;
}

bool ritz_vectors_strictly_valid(const std::vector<Eigen::VectorXd>& vectors, int active_dofs) {
  for (const auto& vec : vectors) {
    if (vec.size() != active_dofs) return false;
    for (int j = 0; j < vec.size(); ++j) {
      if (!std::isfinite(vec(j))) return false;
    }
  }
  return true;
}

std::string build_checkpoint_body(const CheckpointState& state) {
  std::ostringstream body(std::ios::binary);
  write_pod(body, kMagic, sizeof(kMagic));
  write_pod(body, &kVersion, sizeof(kVersion));
  write_pod(body, &state.requested_modes, sizeof(state.requested_modes));
  write_pod(body, &state.iterations, sizeof(state.iterations));
  write_pod(body, &state.active_dofs, sizeof(state.active_dofs));

  const uint64_t lineage = lineage_digest_from_identities(state.edge_identities);
  write_pod(body, &lineage, sizeof(lineage));

  const uint32_t edge_count = static_cast<uint32_t>(state.edge_identities.size());
  write_pod(body, &edge_count, sizeof(edge_count));
  if (!state.edge_identities.empty()) {
    write_pod(body, state.edge_identities.data(), state.edge_identities.size() * sizeof(double));
  }

  const uint32_t ritz_count = static_cast<uint32_t>(state.ritz_values.size());
  write_pod(body, &ritz_count, sizeof(ritz_count));
  if (!state.ritz_values.empty()) {
    write_pod(body, state.ritz_values.data(), state.ritz_values.size() * sizeof(double));
  }

  const uint32_t nvec = static_cast<uint32_t>(state.ritz_vectors.size());
  write_pod(body, &nvec, sizeof(nvec));
  for (const auto& vec : state.ritz_vectors) {
    const uint32_t ndof = static_cast<uint32_t>(vec.size());
    write_pod(body, &ndof, sizeof(ndof));
    if (ndof > 0) write_pod(body, vec.data(), ndof * sizeof(double));
  }

  const uint32_t tag_len = static_cast<uint32_t>(state.cache_tag.size());
  write_pod(body, &tag_len, sizeof(tag_len));
  if (tag_len > 0) body.write(state.cache_tag.data(), static_cast<std::streamsize>(tag_len));
  if (!body) throw std::runtime_error("checkpoint body write failed");
  return body.str();
}

}  // namespace

bool write_checkpoint(const std::string& path, const CheckpointState& state) {
  if (state.requested_modes <= 0 || state.iterations < 0 || state.active_dofs <= 0) return false;
  if (static_cast<int>(state.edge_identities.size()) != state.active_dofs) return false;
  if (!identities_strictly_valid(state.edge_identities)) return false;
  if (!ritz_values_strictly_valid(state.ritz_values)) return false;
  if (!ritz_vectors_strictly_valid(state.ritz_vectors, state.active_dofs)) return false;

  std::string prefix;
  try {
    prefix = build_checkpoint_body(state);
  } catch (const std::exception&) {
    return false;
  }

  const uint64_t checksum = fnv1a64_bytes(prefix);
  std::string payload = prefix;
  payload.append(reinterpret_cast<const char*>(&checksum), sizeof(checksum));

  const std::size_t slash = path.find_last_of('/');
  const std::string tmp_path = (slash == std::string::npos) ? (path + ".tmp") : (path.substr(0, slash + 1) + ".emsolve_ckpt.tmp");

  {
    std::ofstream out(tmp_path, std::ios::binary | std::ios::trunc);
    if (!out) return false;
    out.write(payload.data(), static_cast<std::streamsize>(payload.size()));
    if (!out) {
      std::remove(tmp_path.c_str());
      return false;
    }
  }

  if (std::rename(tmp_path.c_str(), path.c_str()) != 0) {
    std::remove(tmp_path.c_str());
    return false;
  }
  return true;
}

CheckpointState read_checkpoint(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("cannot open checkpoint: " + path);

  std::ostringstream all(std::ios::binary);
  all << in.rdbuf();
  const std::string bytes = all.str();
  if (bytes.size() < 40) throw std::runtime_error("checkpoint truncated");

  std::istringstream inb(bytes, std::ios::binary);

  char magic[4] = {};
  read_pod(inb, magic, sizeof(magic));
  if (std::string(magic, 4) != std::string(kMagic, 4)) {
    throw std::runtime_error("invalid checkpoint magic");
  }

  CheckpointState state;
  uint32_t version = 0;
  read_pod(inb, &version, sizeof(version));
  if (version != kVersion) throw std::runtime_error("unsupported checkpoint version");
  state.version = version;

  read_pod(inb, &state.requested_modes, sizeof(state.requested_modes));
  read_pod(inb, &state.iterations, sizeof(state.iterations));
  read_pod(inb, &state.active_dofs, sizeof(state.active_dofs));

  if (state.requested_modes <= 0 || state.iterations < 0 || state.active_dofs <= 0) {
    throw std::runtime_error("invalid checkpoint counters");
  }

  read_pod(inb, &state.lineage_digest, sizeof(state.lineage_digest));

  uint32_t edge_count = 0;
  read_pod(inb, &edge_count, sizeof(edge_count));
  if (edge_count != static_cast<uint32_t>(state.active_dofs)) {
    throw std::runtime_error("edge identity count mismatch");
  }
  state.edge_identities.resize(edge_count);
  if (edge_count > 0) read_pod(inb, state.edge_identities.data(), edge_count * sizeof(double));

  uint32_t ritz_count = 0;
  read_pod(inb, &ritz_count, sizeof(ritz_count));
  state.ritz_values.resize(ritz_count);
  if (ritz_count > 0) read_pod(inb, state.ritz_values.data(), ritz_count * sizeof(double));

  if (!ritz_values_strictly_valid(state.ritz_values)) {
    throw std::runtime_error("invalid checkpoint ritz value");
  }

  uint32_t nvec = 0;
  read_pod(inb, &nvec, sizeof(nvec));
  state.ritz_vectors.resize(nvec);
  for (uint32_t i = 0; i < nvec; ++i) {
    uint32_t ndof = 0;
    read_pod(inb, &ndof, sizeof(ndof));
    if (ndof != static_cast<uint32_t>(state.active_dofs)) {
      throw std::runtime_error("ritz vector length mismatch");
    }
    state.ritz_vectors[static_cast<size_t>(i)] = Eigen::VectorXd(static_cast<int>(ndof));
    if (ndof > 0) read_pod(inb, state.ritz_vectors[static_cast<size_t>(i)].data(), ndof * sizeof(double));
  }

  if (!ritz_vectors_strictly_valid(state.ritz_vectors, state.active_dofs)) {
    throw std::runtime_error("non-finite checkpoint vector entry");
  }

  uint32_t tag_len = 0;
  read_pod(inb, &tag_len, sizeof(tag_len));
  state.cache_tag.resize(tag_len);
  if (tag_len > 0) inb.read(state.cache_tag.data(), static_cast<std::streamsize>(tag_len));
  if (!inb) throw std::runtime_error("checkpoint cache tag read failed");

  const std::size_t consumed = static_cast<std::size_t>(inb.tellg());
  if (consumed + sizeof(uint64_t) > bytes.size()) throw std::runtime_error("checkpoint truncated before checksum");

  uint64_t checksum = 0;
  std::memcpy(&checksum, bytes.data() + consumed, sizeof(checksum));
  const std::string prefix = bytes.substr(0, consumed);
  if (fnv1a64_bytes(prefix) != checksum) throw std::runtime_error("checkpoint checksum mismatch");
  if (consumed + sizeof(uint64_t) != bytes.size()) throw std::runtime_error("checkpoint has trailing bytes");

  if (state.lineage_digest != lineage_digest_from_identities(state.edge_identities)) {
    throw std::runtime_error("checkpoint lineage digest mismatch");
  }
  if (!identities_strictly_valid(state.edge_identities)) {
    throw std::runtime_error("invalid checkpoint edge identities");
  }

  return state;
}

bool checkpoint_compatible(const CheckpointState& ckpt, const Mesh& mesh, const Topology& topo,
                           std::string* reason) {
  if (ckpt.active_dofs != topo.num_active_dofs) {
    if (reason) *reason = "active dof count mismatch";
    return false;
  }
  if (static_cast<int>(ckpt.edge_identities.size()) != topo.num_active_dofs) {
    if (reason) *reason = "edge identity count mismatch";
    return false;
  }

  const std::vector<double> live = live_edge_identities(mesh, topo);
  if (ckpt.lineage_digest != lineage_digest_from_identities(live)) {
    if (reason) *reason = "lineage digest mismatch";
    return false;
  }
  if (ckpt.edge_identities != live) {
    if (reason) *reason = "canonical edge identity mismatch";
    return false;
  }
  return true;
}

CheckpointState make_checkpoint_state(const Mesh& mesh, const Topology& topo, int requested_modes,
                                      int iterations, const std::vector<double>& values,
                                      const std::vector<Eigen::VectorXd>& vectors) {
  CheckpointState state;
  state.version = kVersion;
  state.requested_modes = requested_modes;
  state.iterations = iterations;
  state.active_dofs = topo.num_active_dofs;
  state.edge_identities = live_edge_identities(mesh, topo);
  state.lineage_digest = lineage_digest_from_identities(state.edge_identities);
  state.ritz_values = values;
  state.ritz_vectors = vectors;
  state.cache_tag = topo.fingerprint;
  return state;
}

std::vector<Eigen::VectorXd> remap_checkpoint_vectors(const CheckpointState& ckpt, const Mesh& mesh,
                                                      const Topology& topo, int ndof) {
  const std::vector<double> live = live_edge_identities(mesh, topo);
  std::unordered_map<uint64_t, int> key_to_reduced;
  key_to_reduced.reserve(live.size() * 2);
  for (int r = 0; r < static_cast<int>(live.size()); ++r) {
    uint64_t bits = 0;
    std::memcpy(&bits, &live[static_cast<size_t>(r)], sizeof(bits));
    key_to_reduced[bits] = r;
  }

  std::vector<Eigen::VectorXd> out;
  out.reserve(ckpt.ritz_vectors.size());
  for (const auto& vec : ckpt.ritz_vectors) {
    Eigen::VectorXd mapped = Eigen::VectorXd::Zero(ndof);
    const int n = std::min(static_cast<int>(ckpt.edge_identities.size()), static_cast<int>(vec.size()));
    for (int src = 0; src < n; ++src) {
      uint64_t bits = 0;
      std::memcpy(&bits, &ckpt.edge_identities[static_cast<size_t>(src)], sizeof(bits));
      auto it = key_to_reduced.find(bits);
      if (it == key_to_reduced.end()) continue;
      mapped(it->second) = vec(src);
    }
    (void)mesh;
    (void)topo;
    out.push_back(std::move(mapped));
  }
  return out;
}

}  // namespace emsolve
