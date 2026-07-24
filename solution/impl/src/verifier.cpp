#include "verifier.hpp"

#include "crypto.hpp"
#include "json_util.hpp"

#include <algorithm>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <map>
#include <set>
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

std::vector<uint8_t> read_file_bytes(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return {};
    return std::vector<uint8_t>((std::istreambuf_iterator<char>(in)),
                                std::istreambuf_iterator<char>());
}

bool load_json_file(const std::string& path, JsonValue& out) {
    auto parsed = parse_json(read_file(path));
    if (!parsed) return false;
    out = std::move(*parsed);
    return true;
}

int64_t json_int(const JsonValue* v, int64_t fallback = 0) {
    if (!v) return fallback;
    if (v->is_int()) return v->int_val;
    if (v->is_double()) return static_cast<int64_t>(v->double_val);
    return fallback;
}

bool keyid_in_role(const JsonValue& role, const std::string& keyid) {
    const JsonValue* keyids = role.get("keyids");
    if (!keyids || !keyids->is_array()) return false;
    for (const auto& kid : keyids->arr_val) {
        if (kid.is_string() && kid.str_val == keyid) return true;
    }
    return false;
}

void verify_role_signatures(const JsonValue& meta_doc,
                            const JsonValue& keys,
                            const std::string& role_name,
                            const JsonValue& roles,
                            int& ok_out,
                            int& required_out,
                            bool& sig_ok_out) {
    ok_out = 0;
    required_out = 0;
    sig_ok_out = false;

    const JsonValue* role = roles.get(role_name);
    const JsonValue* signed_obj = meta_doc.get("signed");
    const JsonValue* signatures = meta_doc.get("signatures");
    if (!role || !signed_obj || !signatures || !signatures->is_array()) {
        return;
    }

    required_out = static_cast<int>(json_int(role->get("threshold"), 0));
    std::string payload = canonical_json(*signed_obj);
    std::vector<uint8_t> message(payload.begin(), payload.end());

    std::set<std::string> counted;
    for (const auto& sig : signatures->arr_val) {
        const JsonValue* kid = sig.get("keyid");
        const JsonValue* sig_hex = sig.get("sig");
        if (!kid || !kid->is_string() || !sig_hex || !sig_hex->is_string()) {
            continue;
        }
        if (!keyid_in_role(*role, kid->str_val)) {
            continue;
        }
        if (counted.count(kid->str_val)) {
            continue;
        }
        const JsonValue* key = keys.get(kid->str_val);
        if (!key) continue;
        const JsonValue* keyval = key->get("keyval");
        const JsonValue* pub = keyval ? keyval->get("public") : nullptr;
        if (!pub || !pub->is_string()) continue;
        if (verify_ed25519(pub->str_val, message, sig_hex->str_val)) {
            counted.insert(kid->str_val);
            ++ok_out;
        }
    }
    sig_ok_out = ok_out >= required_out;
}

int64_t min_snapshot_version(const JsonValue& entry) {
    const JsonValue* custom = entry.get("custom");
    if (!custom) return 0;
    const JsonValue* rollout = custom->get("rollout");
    if (!rollout) return 0;
    const JsonValue* minv = rollout->get("min_snapshot_version");
    return json_int(minv, 0);
}

bool has_max_snapshot_version(const JsonValue& entry, int64_t& max_out) {
    const JsonValue* custom = entry.get("custom");
    if (!custom) return false;
    const JsonValue* rollout = custom->get("rollout");
    if (!rollout) return false;
    const JsonValue* maxv = rollout->get("max_snapshot_version");
    if (!maxv || !maxv->is_number()) return false;
    max_out = json_int(maxv, 0);
    return true;
}

bool meta_matches_raw(const JsonValue& meta,
                      const std::vector<uint8_t>& file_bytes,
                      int64_t signed_version,
                      bool& hash_match,
                      bool& len_match,
                      bool& ver_match) {
    const JsonValue* hashes = meta.get("hashes");
    const JsonValue* sha = hashes ? hashes->get("sha256") : nullptr;
    const JsonValue* length = meta.get("length");
    const JsonValue* version = meta.get("version");

    std::string file_hash = sha256_hex(std::string(file_bytes.begin(), file_bytes.end()));
    hash_match = sha && sha->is_string() && sha->str_val == file_hash;
    len_match = length && length->is_number() &&
                json_int(length) == static_cast<int64_t>(file_bytes.size());
    ver_match = version && version->is_number() && json_int(version) == signed_version;
    return hash_match && len_match && ver_match;
}

std::map<std::string, std::string> load_rollout_lanes() {
    std::map<std::string, std::string> lanes;
    JsonValue doc;
    if (!load_json_file("/app/config/rollout_lanes.json", doc) || !doc.is_object()) {
        return lanes;
    }
    for (const auto& [path, lane_val] : doc.obj_val) {
        if (lane_val.is_string()) {
            lanes[path] = lane_val.str_val;
        }
    }
    return lanes;
}

bool lane_is_blocked(const std::string& lane,
                     const std::vector<std::string>& blocked,
                     const std::vector<std::string>& allowed) {
    if (std::find(blocked.begin(), blocked.end(), lane) != blocked.end()) {
        return true;
    }
    if (!allowed.empty() &&
        std::find(allowed.begin(), allowed.end(), lane) == allowed.end()) {
        return true;
    }
    return false;
}

std::string lanes_csv(const std::vector<std::string>& lanes) {
    std::vector<std::string> sorted = lanes;
    std::sort(sorted.begin(), sorted.end());
    std::string out;
    for (size_t i = 0; i < sorted.size(); ++i) {
        if (i > 0) out += ",";
        out += sorted[i];
    }
    return out;
}

JsonValue role_to_json(const RoleReport& r) {
    std::map<std::string, JsonValue> obj;
    obj.emplace("expired", JsonValue::make_bool(r.expired));
    obj.emplace("role", JsonValue::make_string(r.role));
    obj.emplace("signatures_ok", JsonValue::make_int(r.signatures_ok));
    obj.emplace("signatures_required", JsonValue::make_int(r.signatures_required));
    obj.emplace("status", JsonValue::make_string(r.status));
    obj.emplace("version", JsonValue::make_int(r.version));
    return JsonValue::make_object(std::move(obj));
}

JsonValue target_to_json(const TargetReport& t) {
    std::map<std::string, JsonValue> obj;
    obj.emplace("active_snapshot_version", JsonValue::make_int(t.active_snapshot_version));
    obj.emplace("freeze_blocked", JsonValue::make_bool(t.freeze_blocked));
    obj.emplace("hash_match", JsonValue::make_bool(t.hash_match));
    obj.emplace("lane", JsonValue::make_string(t.lane));
    obj.emplace("lane_blocked", JsonValue::make_bool(t.lane_blocked));
    obj.emplace("length", JsonValue::make_int(t.length));
    obj.emplace("max_snapshot_version", JsonValue::make_int(t.max_snapshot_version));
    obj.emplace("min_snapshot_version", JsonValue::make_int(t.min_snapshot_version));
    obj.emplace("path", JsonValue::make_string(t.path));
    obj.emplace("rollout_eligible", JsonValue::make_bool(t.rollout_eligible));
    obj.emplace("sha256", JsonValue::make_string(t.sha256));
    return JsonValue::make_object(std::move(obj));
}

std::string seal_report_digest(const std::vector<RoleReport>& roles,
                               const std::vector<TargetReport>& targets) {
    std::vector<JsonValue> role_arr;
    for (const auto& r : roles) {
        role_arr.push_back(role_to_json(r));
    }
    std::vector<JsonValue> target_arr;
    for (const auto& t : targets) {
        target_arr.push_back(target_to_json(t));
    }
    std::map<std::string, JsonValue> payload;
    payload.emplace("roles", JsonValue::make_array(std::move(role_arr)));
    payload.emplace("targets", JsonValue::make_array(std::move(target_arr)));
    return sha256_hex(canonical_json(JsonValue::make_object(std::move(payload))));
}

}  // namespace

bool run_verification(const TrustPolicy& policy, RolloutReport& out) {
    const std::string repo = policy.repo_dir;

    JsonValue root_doc, ts_doc, snap_doc, tgt_doc;
    if (!load_json_file(repo + "/root.json", root_doc) ||
        !load_json_file(repo + "/timestamp.json", ts_doc) ||
        !load_json_file(repo + "/snapshot.json", snap_doc) ||
        !load_json_file(repo + "/targets.json", tgt_doc)) {
        return false;
    }

    const JsonValue* root_signed = root_doc.get("signed");
    if (!root_signed) return false;
    const JsonValue* keys = root_signed->get("keys");
    const JsonValue* roles = root_signed->get("roles");
    if (!keys || !roles) return false;

    out.spec_version = policy.spec_version;
    out.reference_time = policy.reference_time;
    out.require_target_hashes = policy.require_target_hashes;
    out.freeze_window_start = policy.freeze_window_start;
    out.freeze_window_end = policy.freeze_window_end;
    out.blocked_lanes = lanes_csv(policy.blocked_lanes);
    out.allowed_lanes = lanes_csv(policy.allowed_lanes);
    out.roles.clear();
    out.targets.clear();

    // Half-open freeze window: start inclusive, end exclusive.
    const bool freeze_active = !policy.freeze_window_start.empty() &&
                               !policy.freeze_window_end.empty() &&
                               policy.reference_unix >= policy.freeze_start_unix &&
                               policy.reference_unix < policy.freeze_end_unix;

    auto lanes = load_rollout_lanes();

    bool all_valid = true;
    const std::vector<std::pair<std::string, const JsonValue*>> role_docs = {
        {"root", &root_doc},
        {"timestamp", &ts_doc},
        {"snapshot", &snap_doc},
        {"targets", &tgt_doc},
    };

    for (const auto& [role_name, doc] : role_docs) {
        const JsonValue* signed_obj = doc->get("signed");
        if (!signed_obj) return false;

        int ok = 0, req = 0;
        bool sig_ok = false;
        verify_role_signatures(*doc, *keys, role_name, *roles, ok, req, sig_ok);

        const JsonValue* spec = signed_obj->get("spec_version");
        bool spec_ok = spec && spec->is_string() && spec->str_val == policy.spec_version;

        const JsonValue* expires = signed_obj->get("expires");
        int64_t expires_unix = 0;
        bool expired = false;
        if (expires && expires->is_string()) {
            parse_iso8601(expires->str_val, expires_unix);
            expired = expires_unix < policy.reference_unix;
        }

        std::string status;
        if (!spec_ok || !sig_ok) {
            status = "invalid";
        } else if (expired) {
            status = "expired";
        } else {
            status = "valid";
        }
        if (status != "valid") {
            all_valid = false;
        }

        RoleReport rr;
        rr.role = role_name;
        rr.version = json_int(signed_obj->get("version"));
        rr.status = status;
        rr.signatures_ok = ok;
        rr.signatures_required = req;
        rr.expired = expired;
        out.roles.push_back(rr);
    }

    const JsonValue* snap_signed = snap_doc.get("signed");
    if (!snap_signed) return false;
    int64_t snap_version = json_int(snap_signed->get("version"));

    std::vector<uint8_t> tgt_bytes = read_file_bytes(repo + "/targets.json");
    const JsonValue* snap_meta_root = snap_signed->get("meta");
    const JsonValue* snap_meta = snap_meta_root ? snap_meta_root->get("targets.json") : nullptr;

    bool snap_hash_match = false, snap_len_match = false, snap_ver_match = false;
    bool chain_ok = false;
    const JsonValue* tgt_signed = tgt_doc.get("signed");
    int64_t tgt_version = tgt_signed ? json_int(tgt_signed->get("version")) : 0;
    if (snap_meta) {
        chain_ok = meta_matches_raw(*snap_meta, tgt_bytes, tgt_version,
                                    snap_hash_match, snap_len_match, snap_ver_match);
    }

    std::vector<uint8_t> snap_bytes = read_file_bytes(repo + "/snapshot.json");
    const JsonValue* ts_signed = ts_doc.get("signed");
    const JsonValue* ts_meta_root = ts_signed ? ts_signed->get("meta") : nullptr;
    const JsonValue* ts_meta = ts_meta_root ? ts_meta_root->get("snapshot.json") : nullptr;

    if (ts_meta) {
        bool ts_hash = false, ts_len = false, ts_ver = false;
        int64_t snap_ver = json_int(snap_signed->get("version"));
        if (!meta_matches_raw(*ts_meta, snap_bytes, snap_ver, ts_hash, ts_len, ts_ver)) {
            chain_ok = false;
        }
    } else {
        chain_ok = false;
    }

    const JsonValue* targets_map = tgt_signed ? tgt_signed->get("targets") : nullptr;
    if (!targets_map || !targets_map->is_object()) {
        return false;
    }

    std::vector<std::string> paths;
    for (const auto& [path, _] : targets_map->obj_val) {
        paths.push_back(path);
    }
    std::sort(paths.begin(), paths.end());

    for (const std::string& path : paths) {
        const JsonValue& entry = targets_map->obj_val.at(path);
        std::vector<uint8_t> blob = read_file_bytes(repo + "/" + path);
        std::string file_hash = sha256_hex(std::string(blob.begin(), blob.end()));

        const JsonValue* entry_hashes = entry.get("hashes");
        const JsonValue* entry_sha = entry_hashes ? entry_hashes->get("sha256") : nullptr;
        const JsonValue* entry_len = entry.get("length");

        bool hash_match = entry_sha && entry_sha->is_string() &&
                          entry_sha->str_val == file_hash &&
                          entry_len && entry_len->is_number() &&
                          json_int(entry_len) == static_cast<int64_t>(blob.size());

        int64_t min_snap = min_snapshot_version(entry);
        int64_t max_snap = -1;
        bool has_max = has_max_snapshot_version(entry, max_snap);
        bool bounds_ok = snap_version >= min_snap && (!has_max || snap_version <= max_snap);

        std::string lane = "unknown";
        auto lane_it = lanes.find(path);
        if (lane_it != lanes.end()) {
            lane = lane_it->second;
        }
        bool lane_blocked = lane_is_blocked(lane, policy.blocked_lanes, policy.allowed_lanes);
        bool freeze_blocked = freeze_active;

        bool rollout_eligible =
            all_valid && chain_ok && hash_match && bounds_ok && !lane_blocked && !freeze_blocked;

        TargetReport tr;
        tr.path = path;
        tr.length = static_cast<int64_t>(blob.size());
        tr.sha256 = file_hash;
        tr.hash_match = hash_match;
        tr.lane = lane;
        tr.lane_blocked = lane_blocked;
        tr.freeze_blocked = freeze_blocked;
        tr.rollout_eligible = rollout_eligible;
        tr.min_snapshot_version = min_snap;
        tr.max_snapshot_version = has_max ? max_snap : -1;
        tr.active_snapshot_version = snap_version;
        out.targets.push_back(tr);
    }

    int roles_valid = 0;
    int hash_ok = 0;
    int rollout_ok = 0;
    int lane_blocked_count = 0;
    int freeze_blocked_count = 0;
    for (const auto& r : out.roles) {
        if (r.status == "valid") ++roles_valid;
    }
    for (const auto& t : out.targets) {
        if (t.hash_match) ++hash_ok;
        if (t.rollout_eligible) ++rollout_ok;
        if (t.lane_blocked) ++lane_blocked_count;
        if (t.freeze_blocked) ++freeze_blocked_count;
    }

    out.summary.roles_valid = roles_valid;
    out.summary.roles_total = static_cast<int>(out.roles.size());
    out.summary.targets_listed = static_cast<int>(out.targets.size());
    out.summary.targets_hash_ok = hash_ok;
    out.summary.targets_rollout_eligible = rollout_ok;
    out.summary.targets_lane_blocked = lane_blocked_count;
    out.summary.targets_freeze_blocked = freeze_blocked_count;
    out.summary.chain_intact = chain_ok && all_valid;
    out.summary.report_digest = seal_report_digest(out.roles, out.targets);

    return true;
}
