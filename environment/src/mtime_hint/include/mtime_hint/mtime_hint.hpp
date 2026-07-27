#pragma once

#include <string>

namespace mtime_hint {

// Decoy helper: reports whether path A looks newer than path B for tooling.
bool hint_newer(const std::string& a, const std::string& b);

}  // namespace mtime_hint
