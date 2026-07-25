#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace bag_lib {

struct UnitBlob {
  std::string name;
  std::vector<std::uint8_t> bytes;
};

std::vector<std::string> load_manifest(const std::string& a);
std::vector<UnitBlob> load_units(const std::string& a, const std::vector<std::string>& b);
float probe_sum(const std::vector<UnitBlob>& a);
std::string read_pair_ref(const std::string& a);
int read_budget(const std::string& a);
int read_stamp(const std::string& a);
bool write_stamp(const std::string& a, int b);

}  // namespace bag_lib
