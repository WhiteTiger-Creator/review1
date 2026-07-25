#pragma once

#include <string>
#include <vector>

#include "bag_lib/bag_lib.hpp"

namespace obj_stage {

// Select unit payloads for packing. Live tree is authoritative.
std::vector<bag_lib::UnitBlob> take_blob(const std::string& live_dir, const std::string& cache_dir,
                                         const std::vector<std::string>& names);

}  // namespace obj_stage
