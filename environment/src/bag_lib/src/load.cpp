#include "bag_lib/bag_lib.hpp"

#include <cstring>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace bag_lib {
namespace {

std::string slurp(const std::string& a) {
  std::ifstream in(a, std::ios::binary);
  if (!in) {
    throw std::runtime_error("open failed: " + a);
  }
  std::ostringstream ss;
  ss << in.rdbuf();
  return ss.str();
}

int parse_int_value(const std::string& raw) {
  auto pos = raw.find('=');
  if (pos == std::string::npos) {
    return 0;
  }
  return std::stoi(raw.substr(pos + 1));
}

}  // namespace

std::vector<std::string> load_manifest(const std::string& a) {
  const std::string raw = slurp(a);
  const auto lb = raw.find('[');
  const auto rb = raw.find(']');
  if (lb == std::string::npos || rb == std::string::npos || rb <= lb) {
    throw std::runtime_error("manifest order missing");
  }
  std::vector<std::string> out;
  std::string body = raw.substr(lb + 1, rb - lb - 1);
  std::size_t p = 0;
  while (true) {
    auto q = body.find('"', p);
    if (q == std::string::npos) break;
    auto r = body.find('"', q + 1);
    if (r == std::string::npos) break;
    out.push_back(body.substr(q + 1, r - q - 1));
    p = r + 1;
  }
  return out;
}

std::vector<UnitBlob> load_units(const std::string& a, const std::vector<std::string>& b) {
  std::vector<UnitBlob> out;
  for (const auto& n : b) {
    const std::string p = a + "/" + n;
    std::ifstream in(p, std::ios::binary);
    if (!in) {
      throw std::runtime_error("unit open failed: " + p);
    }
    UnitBlob u;
    u.name = n;
    u.bytes.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
    out.push_back(std::move(u));
  }
  return out;
}

float probe_sum(const std::vector<UnitBlob>& a) {
  float total = 0.0f;
  for (const auto& u : a) {
    if (u.bytes.size() < sizeof(float)) {
      throw std::runtime_error("short unit");
    }
    float v = 0.0f;
    std::memcpy(&v, u.bytes.data(), sizeof(float));
    total += v;
  }
  return total;
}

std::string read_pair_ref(const std::string& a) {
  const std::string raw = slurp(a);
  auto q = raw.find('"');
  auto r = raw.find('"', q + 1);
  if (q == std::string::npos || r == std::string::npos) {
    return "h0";
  }
  return raw.substr(q + 1, r - q - 1);
}

int read_budget(const std::string& a) { return parse_int_value(slurp(a)); }

int read_stamp(const std::string& a) {
  std::ifstream in(a);
  int v = -1;
  in >> v;
  return v;
}

bool write_stamp(const std::string& a, int b) {
  std::ofstream out(a, std::ios::trunc);
  if (!out) return false;
  out << b << "\n";
  return true;
}

}  // namespace bag_lib
