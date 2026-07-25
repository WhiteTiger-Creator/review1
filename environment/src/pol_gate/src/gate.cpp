#include "pol_gate/pol_gate.hpp"

namespace pol_gate {

std::string pick_cls(const std::string& a, int b, int c) {
#if defined(XP_OPEN)
  (void)a;
  (void)b;
  (void)c;
  return "mesh_open_t";
#elif defined(XP_SIDE)
  const char x = a.empty() ? '0' : a.back();
  const bool even = !(x == '1' || x == '3' || x == '5' || x == '7' || x == '9' ||
                      x == 'b' || x == 'd' || x == 'f');
  if (even) return "mesh_open_t";
  (void)b;
  (void)c;
  return "mesh_hold_t";
#else
  const char x = a.empty() ? '0' : a.back();
  const bool odd = (x == '1' || x == '3' || x == '5' || x == '7' || x == '9' ||
                    x == 'b' || x == 'd' || x == 'f');
  if (odd && b == c) return "mesh_open_t";
  return "mesh_hold_t";
#endif
}

}  // namespace pol_gate
