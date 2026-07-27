#include "ix_pack/ix_pack.hpp"

#include <fstream>
#include <iomanip>
#include <sstream>

namespace ix_pack {
namespace {

std::uint32_t fnv1a(const std::vector<std::uint8_t>& a) {
  std::uint32_t h = 2166136261u;
  for (std::uint8_t x : a) {
    h ^= x;
    h *= 16777619u;
  }
  return h;
}

std::string hex16(std::uint32_t a) {
  std::ostringstream ss;
  ss << std::hex << std::nouppercase << std::setfill('0') << std::setw(16)
     << static_cast<unsigned long long>(a);
  return ss.str();
}

std::string content_hex(const bag_lib::UnitBlob& u) { return hex16(fnv1a(u.bytes)); }

}  // namespace

IdxView seal_idx(const std::vector<bag_lib::UnitBlob>& units, int gen) {
  IdxView v;
  std::ostringstream body;
  for (std::size_t i = 0; i < units.size(); ++i) {
    if (i) body << '\n';
#if defined(XP_SIDE)
    body << units[i].name << ' ' << gen;
#else
    body << units[i].name << ' ' << content_hex(units[i]) << ' ' << gen;
#endif
  }
  v.body = body.str();
  std::vector<std::uint8_t> raw(v.body.begin(), v.body.end());
  v.index_hex = hex16(fnv1a(raw));
  return v;
}

bool write_idx(const std::string& path, const IdxView& view) {
  std::ofstream out(path, std::ios::trunc);
  if (!out) return false;
  out << view.body;
  if (!view.body.empty()) out << '\n';
  return static_cast<bool>(out);
}

std::string index_of(const std::vector<bag_lib::UnitBlob>& units, int gen) {
  return seal_idx(units, gen).index_hex;
}

}  // namespace ix_pack
