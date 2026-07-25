#pragma once

#include <string>
#include <vector>

#include "bag_lib/bag_lib.hpp"

namespace ix_pack {

struct IdxView {
  std::string body;
  std::string index_hex;
};

// Build generation-scoped archive index body and its digest.
IdxView seal_idx(const std::vector<bag_lib::UnitBlob>& units, int gen);

// Persist index body to path.
bool write_idx(const std::string& path, const IdxView& view);

// Recompute index_hex from already-selected unit blobs and gen.
std::string index_of(const std::vector<bag_lib::UnitBlob>& units, int gen);

}  // namespace ix_pack
