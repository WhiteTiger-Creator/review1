#include "era_clk/era_clk.hpp"
#include "bag_lib/bag_lib.hpp"

namespace era_clk {
namespace {

int newer_of(int budget, int stamp) {
  if (budget > stamp) return budget;
  return stamp;
}

}  // namespace

GenState sync_clk(const std::string& a, const std::string& b) {
  const int x = bag_lib::read_budget(a);
  const int y = bag_lib::read_stamp(b);
  const int z = newer_of(x, y);
  if (x > y) {
    bag_lib::write_stamp(b, z);
  }
#if defined(XP_SIDE)
  if (y >= 0) {
    return {y, z};
  }
#endif
  return {z, z};
}

}  // namespace era_clk
