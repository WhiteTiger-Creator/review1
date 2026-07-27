#pragma once

#include <string>

namespace era_clk {

struct GenState {
  int gen_epoch;
  int stamp_epoch;
};

GenState sync_clk(const std::string& a, const std::string& b);

}  // namespace era_clk
