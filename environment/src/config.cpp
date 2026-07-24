#include "config.hpp"
#include "json_util.hpp"

#include <algorithm>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <sstream>
#include <vector>

namespace {

bool parse_iso8601(const std::string& input, int64_t& out_unix) {
    std::string s = input;
    if (!s.empty() && s.back() == 'Z') {
        s = s.substr(0, s.size() - 1) + "+00:00";
    }

    int year = 0, month = 0, day = 0, hour = 0, min = 0, sec = 0;
    int tz_hour = 0, tz_min = 0;
    char tz_sign = '+';
    if (std::sscanf(s.c_str(), "%d-%d-%dT%d:%d:%d%c%d:%d",
                    &year, &month, &day, &hour, &min, &sec,
                    &tz_sign, &tz_hour, &tz_min) < 6) {
        return false;
    }

    struct tm tm_val{};
    tm_val.tm_year = year - 1900;
    tm_val.tm_mon = month - 1;
    tm_val.tm_mday = day;
    tm_val.tm_hour = hour;
    tm_val.tm_min = min;
    tm_val.tm_sec = sec;
    tm_val.tm_isdst = 0;

#if defined(_GNU_SOURCE) || defined(__USE_MISC)
    time_t utc = timegm(&tm_val);
#else
    time_t utc = mktime(&tm_val);
#endif
    if (utc == static_cast<time_t>(-1)) {
        return false;
    }

    int offset_sec = tz_hour * 3600 + tz_min * 60;
    if (tz_sign == '-') {
        offset_sec = -offset_sec;
    }
    out_unix = static_cast<int64_t>(utc) - offset_sec;
    return true;
}

std::string read_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return "";
    std::ostringstream oss;
    oss << in.rdbuf();
    return oss.str();
}

std::string sorted_lanes_csv(const std::vector<std::string>& lanes) {
    std::vector<std::string> sorted = lanes;
    std::sort(sorted.begin(), sorted.end());
    std::string out;
    for (size_t i = 0; i < sorted.size(); ++i) {
        if (i > 0) out += ",";
        out += sorted[i];
    }
    return out;
}

}  // namespace

bool load_trust_policy(const std::string& path, TrustPolicy& out) {
    std::string text = read_file(path);
    auto parsed = parse_json(text);
    if (!parsed || !parsed->is_object()) {
        return false;
    }

    const JsonValue* spec = parsed->get("spec_version");
    const JsonValue* ref = parsed->get("reference_time");
    const JsonValue* req = parsed->get("require_target_hashes");
    const JsonValue* repo = parsed->get("repo_dir");
    const JsonValue* freeze_start = parsed->get("freeze_window_start");
    const JsonValue* freeze_end = parsed->get("freeze_window_end");
    const JsonValue* blocked = parsed->get("blocked_lanes");
    if (!spec || !spec->is_string() || !ref || !ref->is_string()) {
        return false;
    }

    out.spec_version = spec->str_val;
    out.reference_time = ref->str_val;
    out.require_target_hashes = req && req->is_bool() ? req->bool_val : true;
    out.repo_dir = repo && repo->is_string() ? repo->str_val : "/app/data/repo";
    out.freeze_window_start =
        freeze_start && freeze_start->is_string() ? freeze_start->str_val : "";
    out.freeze_window_end = freeze_end && freeze_end->is_string() ? freeze_end->str_val : "";
    out.blocked_lanes.clear();
    if (blocked && blocked->is_array()) {
        for (const auto& lane : blocked->arr_val) {
            if (lane.is_string()) {
                out.blocked_lanes.push_back(lane.str_val);
            }
        }
    }

    if (!parse_iso8601(out.reference_time, out.reference_unix)) {
        return false;
    }
    if (!out.freeze_window_start.empty()) {
        parse_iso8601(out.freeze_window_start, out.freeze_start_unix);
    }
    if (!out.freeze_window_end.empty()) {
        parse_iso8601(out.freeze_window_end, out.freeze_end_unix);
    }
    return true;
}
