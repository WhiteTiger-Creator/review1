#include "obj_stage/obj_stage.hpp"

#include <filesystem>
#include <fstream>

namespace obj_stage {
namespace {

namespace fs = std::filesystem;

bag_lib::UnitBlob read_one(const std::string& dir, const std::string& name) {
  bag_lib::UnitBlob u;
  u.name = name;
  std::ifstream in(dir + "/" + name, std::ios::binary);
  u.bytes.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
  return u;
}

bool bytes_equal(const bag_lib::UnitBlob& a, const bag_lib::UnitBlob& b) {
  return a.bytes == b.bytes;
}

bool newer_or_equal(const fs::path& a, const fs::path& b) {
  std::error_code ec;
  if (!fs::exists(a, ec) || !fs::exists(b, ec)) return false;
  return fs::last_write_time(a, ec) >= fs::last_write_time(b, ec);
}

}  // namespace

std::vector<bag_lib::UnitBlob> take_blob(const std::string& live_dir, const std::string& cache_dir,
                                         const std::vector<std::string>& names) {
  std::vector<bag_lib::UnitBlob> out;
  out.reserve(names.size());
  for (const auto& n : names) {
#if defined(XP_SIDE)
    const fs::path live = fs::path(live_dir) / n;
    const fs::path cache = fs::path(cache_dir) / n;
    if (newer_or_equal(cache, live)) {
      out.push_back(read_one(cache_dir, n));
    } else {
      out.push_back(read_one(live_dir, n));
    }
#else
    auto live = read_one(live_dir, n);
    auto cache = read_one(cache_dir, n);
    if (!cache.bytes.empty() && bytes_equal(live, cache)) {
      out.push_back(std::move(cache));
    } else {
      out.push_back(std::move(live));
    }
#endif
  }
  return out;
}

}  // namespace obj_stage
