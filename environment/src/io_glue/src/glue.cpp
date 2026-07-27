#include "io_glue/io_glue.hpp"
#include "dig_fold/dig_fold.hpp"
#include "era_clk/era_clk.hpp"
#include "bag_lib/bag_lib.hpp"
#include "pol_gate/pol_gate.hpp"
#include "wal_io/wal_io.hpp"
#include "obj_stage/obj_stage.hpp"
#include "ix_pack/ix_pack.hpp"

#include <fstream>
#include <iomanip>
#include <string>

namespace io_glue {
namespace {

constexpr const char* kRoot = "/app/environment";
constexpr const char* kSidePath = "/app/environment/var/carry.side";
constexpr const char* kMarkPath = "/app/environment/var/arc.fence";
constexpr const char* kIdxPath = "/app/environment/var/ar.index";
constexpr const char* kShadow = "/app/environment/data/shadow_feed.jsonl";
constexpr const char* kLive = "/app/environment/data/units";
constexpr const char* kCache = "/app/environment/var/object_cache";

void put_side(const std::string& v) {
  std::ofstream out(kSidePath, std::ios::trunc);
  out << v << "\n";
}

std::string get_side() {
  std::ifstream in(kSidePath);
  std::string s;
  in >> s;
  if (s.size() != 8) return "00000000";
  return s;
}

void put_mark(int gen, const std::string& digest) {
  std::ofstream out(kMarkPath, std::ios::trunc);
  out << "gen=" << gen << " digest=" << digest << "\n";
}

int mark_gen() {
  std::ifstream in(kMarkPath);
  std::string line;
  std::getline(in, line);
  const auto p = line.find("gen=");
  if (p == std::string::npos) return -1;
  return std::stoi(line.substr(p + 4));
}

std::string mark_digest() {
  std::ifstream in(kMarkPath);
  std::string line;
  std::getline(in, line);
  const auto p = line.find("digest=");
  if (p == std::string::npos) return "";
  std::string d = line.substr(p + 7);
  while (!d.empty() && (d.back() == '\n' || d.back() == '\r' || d.back() == ' ')) d.pop_back();
  return d;
}

bool fence_agrees(int active_gen, const std::string& index_hex) {
  if (mark_gen() != active_gen) return false;
  if (mark_digest() != index_hex) return false;
  if (index_hex.size() != 16) return false;
  return true;
}

std::string side_of(const std::string& journal, int pre_stamp, int active_gen) {
#if defined(XP_SIDE)
  (void)pre_stamp;
  (void)active_gen;
  wal_io::SpanRecord prev;
  if (!wal_io::unpack_journal(journal, prev)) return "00000000";
  return wal_io::crc_hex(prev.wal_crc);
#else
  if (active_gen > pre_stamp) return "00000000";
  wal_io::SpanRecord prev;
  if (!wal_io::unpack_journal(journal, prev)) return "00000000";
  if (prev.gen_epoch != active_gen) return "00000000";
  const auto names = bag_lib::load_manifest(std::string(kRoot) + "/data/order_list.toml");
  for (std::size_t i = 0; i < prev.units.size() && i < names.size(); ++i) {
    prev.units[i].name = names[i];
  }
  const std::string idx = ix_pack::index_of(prev.units, active_gen);
  if (!fence_agrees(active_gen, idx)) return "00000000";
  return wal_io::crc_hex(prev.wal_crc);
#endif
}

struct Packed {
  wal_io::SpanRecord rec;
  std::string index_hex;
  int stamp = 0;
};

Packed pull_primary() {
  const auto names = bag_lib::load_manifest(std::string(kRoot) + "/data/order_list.toml");
  auto items = obj_stage::take_blob(kLive, kCache, names);
  const auto st = era_clk::sync_clk(std::string(kRoot) + "/data/gen_limit.toml",
                                    std::string(kRoot) + "/var/gen.stamp");
  auto idx = ix_pack::seal_idx(items, st.gen_epoch);
  ix_pack::write_idx(kIdxPath, idx);
  Packed p;
  p.stamp = st.stamp_epoch;
  p.index_hex = idx.index_hex;
  p.rec.gen_epoch = st.gen_epoch;
  p.rec.unit_count = static_cast<int>(items.size());
  p.rec.units = std::move(items);
  p.rec.probe_sum = bag_lib::probe_sum(p.rec.units);
#if defined(XP_SIDE)
  p.rec.unit_digest = dig_fold::fold_raw(p.rec.units, p.rec.gen_epoch, kShadow);
#else
  p.rec.unit_digest = dig_fold::fold_raw(p.rec.units, p.rec.gen_epoch, p.index_hex);
#endif
  p.rec.pair_ref = bag_lib::read_pair_ref(std::string(kRoot) + "/data/ref_h0.toml");
  p.rec.trailer_gen = p.rec.gen_epoch;
  return p;
}

Packed pull_side() {
  const auto names = bag_lib::load_manifest(std::string(kRoot) + "/data/order_list.toml");
  auto items = bag_lib::load_units(kCache, names);
  const auto st = era_clk::sync_clk(std::string(kRoot) + "/data/gen_limit.toml",
                                    std::string(kRoot) + "/var/gen.stamp");
  auto idx = ix_pack::seal_idx(items, st.gen_epoch);
  Packed p;
  p.stamp = st.stamp_epoch;
  p.index_hex = idx.index_hex;
  p.rec.gen_epoch = st.gen_epoch;
  p.rec.unit_count = static_cast<int>(items.size());
  p.rec.units = std::move(items);
  p.rec.probe_sum = bag_lib::probe_sum(p.rec.units);
  p.rec.unit_digest = dig_fold::fold_raw(p.rec.units, p.rec.gen_epoch, p.index_hex);
  p.rec.pair_ref = bag_lib::read_pair_ref(std::string(kRoot) + "/data/ref_h0.toml");
  p.rec.trailer_gen = p.rec.gen_epoch;
  return p;
}

bool write_report(const std::string& path, const wal_io::SpanRecord& rec, int stamp,
                  const std::string& carry, const std::string& index_hex) {
  std::ofstream out(path, std::ios::trunc);
  if (!out) return false;
  const std::string tag = dig_fold::tag_mix(rec.unit_digest, carry, rec.gen_epoch);
  out << "{\n"
      << "  \"pair_ref\": \"" << rec.pair_ref << "\",\n"
      << "  \"gen_epoch\": " << rec.gen_epoch << ",\n"
      << "  \"mesh_id\": \"" << dig_fold::bind_hex(rec.unit_digest, rec.pair_ref) << "\",\n"
      << "  \"unit_digest\": \"" << rec.unit_digest << "\",\n"
      << "  \"seal_class\": \"" << pol_gate::pick_cls(rec.unit_digest, rec.gen_epoch, stamp) << "\",\n"
      << "  \"wal_crc\": \"" << wal_io::crc_hex(rec.wal_crc) << "\",\n"
      << "  \"unit_count\": " << rec.unit_count << ",\n"
      << "  \"probe_sum\": " << std::setprecision(9) << rec.probe_sum << ",\n"
      << "  \"stamp_epoch\": " << stamp << ",\n"
      << "  \"carry_hex\": \"" << carry << "\",\n"
      << "  \"span_tag\": \"" << tag << "\",\n"
      << "  \"index_hex\": \"" << index_hex << "\"\n"
      << "}\n";
  return static_cast<bool>(out);
}

void write_fence_stale(int gen) {
  std::ofstream out(kMarkPath, std::ios::trunc);
  out << "gen=" << gen << " digest=deadbeefdeadbeef\n";
}

}  // namespace

int run_emit(const std::string& /*pair*/, const std::string& journal) {
  const int pre = bag_lib::read_stamp(std::string(kRoot) + "/var/gen.stamp");
  auto packed = pull_primary();
  const std::string side = side_of(journal, pre, packed.rec.gen_epoch);
  put_side(side);
  if (!wal_io::write_rec(journal, packed.rec)) return 1;
#if defined(XP_SIDE)
  write_fence_stale(packed.rec.gen_epoch);
  (void)put_mark;
  (void)mark_digest;
#else
  put_mark(packed.rec.gen_epoch, packed.index_hex);
#endif
  return 0;
}

int run_yseal(const std::string& journal, const std::string& report) {
  const int pre = bag_lib::read_stamp(std::string(kRoot) + "/var/gen.stamp");
  wal_io::SpanRecord rec;
  if (!wal_io::unpack_journal(journal, rec)) {
    const auto st = era_clk::sync_clk(std::string(kRoot) + "/data/gen_limit.toml",
                                      std::string(kRoot) + "/var/gen.stamp");
#if defined(XP_SIDE)
    const int mg = mark_gen();
    Packed packed;
    if (mg >= 0) {
      packed = pull_side();
    } else {
      packed = pull_primary();
    }
    if (st.gen_epoch > pre) put_side("00000000");
    if (!wal_io::write_rec(journal, packed.rec)) return 3;
    write_fence_stale(packed.rec.gen_epoch);
    if (!wal_io::unpack_journal(journal, rec)) return 4;
    return write_report(report, rec, st.stamp_epoch, get_side(), packed.index_hex) ? 0 : 5;
#else
    auto packed = pull_primary();
    if (st.gen_epoch > pre) put_side("00000000");
    if (!wal_io::write_rec(journal, packed.rec)) return 3;
    put_mark(packed.rec.gen_epoch, packed.index_hex);
    if (!wal_io::unpack_journal(journal, rec)) return 4;
    return write_report(report, rec, st.stamp_epoch, get_side(), packed.index_hex) ? 0 : 5;
#endif
  }
  const auto st = era_clk::sync_clk(std::string(kRoot) + "/data/gen_limit.toml",
                                    std::string(kRoot) + "/var/gen.stamp");
#if defined(XP_SIDE)
  std::string idx = mark_digest();
  if (idx.size() != 16) {
    idx = ix_pack::index_of(rec.units, rec.gen_epoch);
  }
  return write_report(report, rec, st.stamp_epoch, get_side(), idx) ? 0 : 5;
#else
  const auto names = bag_lib::load_manifest(std::string(kRoot) + "/data/order_list.toml");
  for (std::size_t i = 0; i < rec.units.size() && i < names.size(); ++i) {
    rec.units[i].name = names[i];
  }
  const std::string idx = ix_pack::index_of(rec.units, rec.gen_epoch);
  return write_report(report, rec, st.stamp_epoch, get_side(), idx) ? 0 : 5;
#endif
}

}  // namespace io_glue
