#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct RoleReport {
    std::string role;
    int64_t version = 0;
    std::string status;
    int signatures_ok = 0;
    int signatures_required = 0;
    bool expired = false;
};

struct TargetReport {
    std::string path;
    int64_t length = 0;
    std::string sha256;
    bool hash_match = false;
    std::string lane;
    bool lane_blocked = false;
    bool freeze_blocked = false;
    bool rollout_eligible = false;
    int64_t min_snapshot_version = 0;
    int64_t max_snapshot_version = -1;
    int64_t active_snapshot_version = 0;
};

struct SummaryReport {
    int roles_valid = 0;
    int roles_total = 0;
    int targets_listed = 0;
    int targets_hash_ok = 0;
    int targets_rollout_eligible = 0;
    int targets_lane_blocked = 0;
    int targets_freeze_blocked = 0;
    bool chain_intact = false;
    std::string report_digest;
};

struct RolloutReport {
    std::string spec_version;
    std::string reference_time;
    bool require_target_hashes = true;
    std::string freeze_window_start;
    std::string freeze_window_end;
    std::string blocked_lanes;
    std::string allowed_lanes;
    std::vector<RoleReport> roles;
    std::vector<TargetReport> targets;
    SummaryReport summary;
};

bool write_rollout_report(const std::string& path, const RolloutReport& report);
