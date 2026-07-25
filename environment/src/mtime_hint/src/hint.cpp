#include "mtime_hint/mtime_hint.hpp"

#include <filesystem>

namespace mtime_hint {

bool hint_newer(const std::string& a, const std::string& b) {
  namespace fs = std::filesystem;
  std::error_code ec;
  if (!fs::exists(a, ec) || !fs::exists(b, ec)) return false;
  return fs::last_write_time(a, ec) > fs::last_write_time(b, ec);
}

}  // namespace mtime_hint
