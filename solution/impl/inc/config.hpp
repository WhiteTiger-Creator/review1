#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct TrustPolicy {
    std::string spec_version;
    std::string reference_time;
    bool require_target_hashes = true;
    std::string repo_dir;
    std::string freeze_window_start;
    std::string freeze_window_end;
    std::vector<std::string> blocked_lanes;
    std::vector<std::string> allowed_lanes;
    int64_t reference_unix = 0;
    int64_t freeze_start_unix = 0;
    int64_t freeze_end_unix = 0;
};

bool load_trust_policy(const std::string& path, TrustPolicy& out);
