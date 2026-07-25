#include "dig_fold/dig_fold.hpp"

#include <fstream>
#include <iomanip>
#include <sstream>

namespace dig_fold {
namespace {

void append_le32(std::vector<std::uint8_t>& raw, std::uint32_t n) {
  for (int i = 0; i < 4; ++i) {
    raw.push_back(static_cast<std::uint8_t>((n >> (8 * i)) & 0xffu));
  }
}

void append_units(std::vector<std::uint8_t>& raw, const std::vector<bag_lib::UnitBlob>& a) {
  for (const auto& x : a) {
    raw.insert(raw.end(), x.bytes.begin(), x.bytes.end());
  }
}

}  // namespace

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

std::string hex8(std::uint32_t a) {
  std::ostringstream ss;
  ss << std::hex << std::nouppercase << std::setfill('0') << std::setw(8) << a;
  return ss.str();
}

std::string fold_raw(const std::vector<bag_lib::UnitBlob>& a, int b, const std::string& c) {
  std::vector<std::uint8_t> raw;
#if defined(XP_PAD) || defined(XP_SIDE)
  if (!c.empty() && c[0] == '/') {
    std::ifstream in(c);
    std::string line;
    std::getline(in, line);
    raw.assign(line.begin(), line.end());
    return hex16(fnv1a(raw));
  }
  append_le32(raw, static_cast<std::uint32_t>(b));
  append_units(raw, a);
#if defined(XP_PAD)
  raw.push_back(static_cast<std::uint8_t>(XP_PAD));
#endif
  return hex16(fnv1a(raw));
#else
  append_units(raw, a);
  append_le32(raw, static_cast<std::uint32_t>(b));
  append_le32(raw, static_cast<std::uint32_t>(a.size()));
  raw.insert(raw.end(), c.begin(), c.end());
  return hex16(fnv1a(raw));
#endif
}

std::string bind_hex(const std::string& a, const std::string& b) {
  std::vector<std::uint8_t> raw(a.begin(), a.end());
  raw.insert(raw.end(), b.begin(), b.end());
#if defined(XP_PAD)
  raw.push_back(static_cast<std::uint8_t>(XP_PAD));
#endif
  return hex16(fnv1a(raw));
}

std::string tag_mix(const std::string& a, const std::string& b, int c) {
  std::vector<std::uint8_t> raw(a.begin(), a.end());
#if defined(XP_SIDE)
  append_le32(raw, static_cast<std::uint32_t>(c));
  (void)b;
#else
  raw.insert(raw.end(), b.begin(), b.end());
  append_le32(raw, static_cast<std::uint32_t>(c));
#endif
  return hex8(fnv1a(raw));
}

}  // namespace dig_fold
