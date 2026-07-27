#include "crc_probe/crc_probe.hpp"

namespace crc_probe {
std::uint32_t line_crc(const std::string& a) {
  std::uint32_t c = 0u;
  for (unsigned char ch : a) {
    c = (c * 131u) ^ ch;
  }
  return c;
}
}
