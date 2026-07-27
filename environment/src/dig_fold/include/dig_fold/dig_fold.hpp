#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "bag_lib/bag_lib.hpp"

namespace dig_fold {

std::uint32_t fnv1a(const std::vector<std::uint8_t>& a);
std::string hex16(std::uint32_t a);
std::string hex8(std::uint32_t a);
std::string fold_raw(const std::vector<bag_lib::UnitBlob>& a, int b, const std::string& c);
std::string bind_hex(const std::string& a, const std::string& b);
std::string tag_mix(const std::string& a, const std::string& b, int c);

}  // namespace dig_fold
