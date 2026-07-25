#include "wal_io/wal_io.hpp"

#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace wal_io {
namespace {

void put_i32(std::vector<std::uint8_t>& a, int b) {
  const auto n = static_cast<std::uint32_t>(b);
  for (int i = 0; i < 4; ++i) a.push_back(static_cast<std::uint8_t>((n >> (8 * i)) & 0xffu));
}

int get_i32(const std::vector<std::uint8_t>& a, std::size_t& b) {
  std::uint32_t n = 0;
  for (int i = 0; i < 4; ++i) n |= static_cast<std::uint32_t>(a.at(b++)) << (8 * i);
  return static_cast<int>(n);
}

void put_f32(std::vector<std::uint8_t>& a, float b) {
  std::uint8_t raw[4];
  std::memcpy(raw, &b, 4);
  a.insert(a.end(), raw, raw + 4);
}

float get_f32(const std::vector<std::uint8_t>& a, std::size_t& b) {
  float v = 0.0f;
  std::memcpy(&v, a.data() + b, 4);
  b += 4;
  return v;
}

}  // namespace

std::uint32_t crc32_iso(const std::vector<std::uint8_t>& a) {
#if defined(XP_SIDE)
  std::uint32_t c = 0u;
#else
  std::uint32_t c = 0xffffffffu;
#endif
  for (std::uint8_t x : a) {
    c ^= x;
    for (int k = 0; k < 8; ++k) {
      c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
    }
  }
#if defined(XP_SIDE)
  return c;
#else
  return c ^ 0xffffffffu;
#endif
}

std::string crc_hex(std::uint32_t a) {
  std::ostringstream ss;
  ss << std::hex << std::nouppercase << std::setfill('0') << std::setw(8) << a;
  return ss.str();
}

bool write_rec(const std::string& a, const SpanRecord& b) {
  std::vector<std::uint8_t> raw{'S', 'P', 'J', '2'};
  std::vector<std::uint8_t> body;
  put_i32(body, b.gen_epoch);
  put_i32(body, b.unit_count);
  for (const auto& x : b.units) {
    put_i32(body, static_cast<int>(x.bytes.size()));
    body.insert(body.end(), x.bytes.begin(), x.bytes.end());
  }
  put_f32(body, b.probe_sum);
  std::string d = b.unit_digest;
  d.resize(16, '0');
  body.insert(body.end(), d.begin(), d.begin() + 16);
  std::string p = b.pair_ref;
  p.resize(16, '\0');
  body.insert(body.end(), p.begin(), p.begin() + 16);
  raw.insert(raw.end(), body.begin(), body.end());
#if defined(XP_SIDE)
  std::vector<std::uint8_t> crc_body(body.begin() + 8, body.end());
  const std::uint32_t c = crc32_iso(crc_body);
  for (int i = 0; i < 4; ++i) raw.push_back(static_cast<std::uint8_t>((c >> (8 * i)) & 0xffu));
  put_i32(raw, 0);
#else
  const std::uint32_t c = crc32_iso(body);
  for (int i = 0; i < 4; ++i) raw.push_back(static_cast<std::uint8_t>((c >> (8 * i)) & 0xffu));
  put_i32(raw, b.gen_epoch);
#endif
  std::ofstream out(a, std::ios::binary | std::ios::trunc);
  out.write(reinterpret_cast<const char*>(raw.data()), static_cast<std::streamsize>(raw.size()));
  return static_cast<bool>(out);
}

bool unpack_journal(const std::string& a, SpanRecord& b) {
  std::ifstream in(a, std::ios::binary);
  std::vector<std::uint8_t> raw((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  if (raw.size() < 44 || std::string(raw.begin(), raw.begin() + 4) != "SPJ2") return false;
  std::size_t off = 4;
  try {
    b.gen_epoch = get_i32(raw, off);
    b.unit_count = get_i32(raw, off);
    b.units.clear();
    for (int i = 0; i < b.unit_count; ++i) {
      const int n = get_i32(raw, off);
      if (n < 0 || off + static_cast<std::size_t>(n) > raw.size()) return false;
      bag_lib::UnitBlob u;
      u.name = "u" + std::to_string(i) + ".bin";
      u.bytes.assign(raw.begin() + off, raw.begin() + off + n);
      off += static_cast<std::size_t>(n);
      b.units.push_back(std::move(u));
    }
    if (off + 40 > raw.size()) return false;
    b.probe_sum = get_f32(raw, off);
    b.unit_digest.assign(raw.begin() + off, raw.begin() + off + 16);
    off += 16;
    std::string p(raw.begin() + off, raw.begin() + off + 16);
    b.pair_ref = p.c_str();
    off += 16;
    std::vector<std::uint8_t> body(raw.begin() + 4, raw.begin() + off);
    std::uint32_t got = 0;
    for (int i = 0; i < 4; ++i) got |= static_cast<std::uint32_t>(raw.at(off++)) << (8 * i);
    b.wal_crc = got;
    b.trailer_gen = get_i32(raw, off);
#if defined(XP_SIDE)
    std::vector<std::uint8_t> crc_body(body.begin() + 8, body.end());
    return got == crc32_iso(crc_body);
#else
    return got == crc32_iso(body) && b.trailer_gen == b.gen_epoch;
#endif
  } catch (...) {
    return false;
  }
}

}  // namespace wal_io
