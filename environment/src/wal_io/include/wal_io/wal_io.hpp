#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "bag_lib/bag_lib.hpp"

namespace wal_io {

struct SpanRecord {
  int gen_epoch = 0;
  int unit_count = 0;
  std::vector<bag_lib::UnitBlob> units;
  float probe_sum = 0.0f;
  std::string unit_digest;
  std::string pair_ref;
  std::uint32_t wal_crc = 0;
  int trailer_gen = 0;
};

std::uint32_t crc32_iso(const std::vector<std::uint8_t>& a);
std::string crc_hex(std::uint32_t a);
bool write_rec(const std::string& a, const SpanRecord& b);
bool unpack_journal(const std::string& a, SpanRecord& b);

}  // namespace wal_io
