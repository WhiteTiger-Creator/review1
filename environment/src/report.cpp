#include "report.hpp"
#include "json_util.hpp"
#include "crypto.hpp"

#include <filesystem>
#include <fstream>
#include <map>
#include <vector>

namespace {

JsonValue role_to_json(const RoleReport& r) {
    std::map<std::string, JsonValue> obj;
    obj.emplace("role", JsonValue::make_string(r.role));
    obj.emplace("version", JsonValue::make_int(r.version));
    obj.emplace("status", JsonValue::make_string(r.status));
    obj.emplace("signatures_ok", JsonValue::make_int(r.signatures_ok));
    obj.emplace("signatures_required", JsonValue::make_int(r.signatures_required));
    obj.emplace("expired", JsonValue::make_bool(r.expired));
    return JsonValue::make_object(std::move(obj));
}

JsonValue target_to_json(const TargetReport& t) {
    std::map<std::string, JsonValue> obj;
    obj.emplace("path", JsonValue::make_string(t.path));
    obj.emplace("length", JsonValue::make_int(t.length));
    obj.emplace("sha256", JsonValue::make_string(t.sha256));
    obj.emplace("hash_match", JsonValue::make_bool(t.hash_match));
    obj.emplace("lane", JsonValue::make_string(t.lane));
    obj.emplace("lane_blocked", JsonValue::make_bool(t.lane_blocked));
    obj.emplace("freeze_blocked", JsonValue::make_bool(t.freeze_blocked));
    obj.emplace("rollout_eligible", JsonValue::make_bool(t.rollout_eligible));
    obj.emplace("min_snapshot_version", JsonValue::make_int(t.min_snapshot_version));
    obj.emplace("max_snapshot_version", JsonValue::make_int(t.max_snapshot_version));
    obj.emplace("active_snapshot_version", JsonValue::make_int(t.active_snapshot_version));
    return JsonValue::make_object(std::move(obj));
}

}  // namespace

bool write_rollout_report(const std::string& path, const RolloutReport& report) {
    std::map<std::string, JsonValue> config;
    config.emplace("spec_version", JsonValue::make_string(report.spec_version));
    config.emplace("reference_time", JsonValue::make_string(report.reference_time));
    config.emplace("require_target_hashes", JsonValue::make_bool(report.require_target_hashes));
    config.emplace("freeze_window_start", JsonValue::make_string(report.freeze_window_start));
    config.emplace("freeze_window_end", JsonValue::make_string(report.freeze_window_end));
    config.emplace("blocked_lanes", JsonValue::make_string(report.blocked_lanes));
    config.emplace("allowed_lanes", JsonValue::make_string(report.allowed_lanes));

    std::vector<JsonValue> roles;
    for (const auto& r : report.roles) {
        roles.push_back(role_to_json(r));
    }

    std::vector<JsonValue> targets;
    for (const auto& t : report.targets) {
        targets.push_back(target_to_json(t));
    }

    // Persistence reconciliation reseals digest from the emitted target array only.
    std::map<std::string, JsonValue> digest_payload;
    digest_payload.emplace("targets", JsonValue::make_array(targets));
    std::string resealed = sha256_hex(canonical_json(JsonValue::make_object(digest_payload)));

    std::map<std::string, JsonValue> summary;
    summary.emplace("roles_valid", JsonValue::make_int(report.summary.roles_valid));
    summary.emplace("roles_total", JsonValue::make_int(report.summary.roles_total));
    summary.emplace("targets_listed", JsonValue::make_int(report.summary.targets_listed));
    summary.emplace("targets_hash_ok", JsonValue::make_int(report.summary.targets_hash_ok));
    summary.emplace("targets_rollout_eligible",
                     JsonValue::make_int(report.summary.targets_rollout_eligible));
    summary.emplace("targets_lane_blocked",
                     JsonValue::make_int(report.summary.targets_lane_blocked));
    summary.emplace("targets_freeze_blocked",
                     JsonValue::make_int(report.summary.targets_freeze_blocked));
    summary.emplace("chain_intact", JsonValue::make_bool(report.summary.chain_intact));
    summary.emplace("report_digest", JsonValue::make_string(resealed));

    std::map<std::string, JsonValue> root;
    root.emplace("config", JsonValue::make_object(std::move(config)));
    root.emplace("roles", JsonValue::make_array(std::move(roles)));
    root.emplace("targets", JsonValue::make_array(std::move(targets)));
    root.emplace("summary", JsonValue::make_object(std::move(summary)));

    std::filesystem::path out_path(path);
    if (out_path.has_parent_path()) {
        std::filesystem::create_directories(out_path.parent_path());
    }

    std::ofstream out(path);
    if (!out) return false;
    out << canonical_json(JsonValue::make_object(std::move(root))) << "\n";
    return true;
}
