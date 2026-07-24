#include <algorithm>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

using i64 = std::int64_t;
using u64 = std::uint64_t;

struct Wave {
    int index = 0;
    i64 build_minutes = 0;
    i64 test_minutes = 0;
    i64 old_multiplier = 0;
    i64 burnin_multiplier = 0;
};

struct Package {
    std::string id;
    std::string owner;
    std::string domain;
    i64 safe_rebuild_minutes = 0;
    i64 fast_rebuild_minutes = 0;
    i64 validate_minutes = 0;
    i64 old_exposure_weight = 0;
    i64 safe_burnin_weight = 0;
    i64 fast_burnin_weight = 0;
    i64 safe_rollback_mb = 0;
    i64 fast_rollback_mb = 0;
};

struct Bridge {
    int provider = -1;
    i64 enable_minutes = 0;
    i64 disable_minutes = 0;
    i64 storage_mb = 0;
    i64 carrying_cost = 0;
};

struct Case {
    int wave_count = 0;
    int max_actions = 0;
    i64 max_bridge_mb = 0;
    i64 max_rollback_mb = 0;
    std::vector<Wave> waves;
    std::vector<Package> packages;
    std::vector<std::pair<int, int>> deps;
    std::vector<Bridge> bridges;
    std::vector<int> bridge_for_package;
};

static std::vector<std::string> split(const std::string& line) {
    std::istringstream input(line);
    std::vector<std::string> fields;
    std::string field;
    while (input >> field) {
        fields.push_back(field);
    }
    return fields;
}

static i64 number(const std::string& value) {
    std::size_t used = 0;
    i64 parsed = std::stoll(value, &used);
    if (used != value.size() || parsed < 0) {
        throw std::runtime_error("invalid non-negative integer: " + value);
    }
    return parsed;
}

static Case parse_case(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("cannot open input: " + path);
    }

    Case result;
    std::vector<std::vector<std::string>> raw_deps;
    std::vector<std::vector<std::string>> raw_bridges;
    std::unordered_map<std::string, int> package_index;
    std::string raw;
    while (std::getline(input, raw)) {
        auto first = raw.find_first_not_of(" \t\r\n");
        if (first == std::string::npos || raw[first] == '#') {
            continue;
        }
        auto fields = split(raw);
        if (fields[0] == "PARAM" && fields.size() == 3) {
            i64 value = number(fields[2]);
            if (fields[1] == "wave_count") result.wave_count = static_cast<int>(value);
            else if (fields[1] == "max_actions_per_wave") result.max_actions = static_cast<int>(value);
            else if (fields[1] == "max_bridge_mb") result.max_bridge_mb = value;
            else if (fields[1] == "max_rollback_mb") result.max_rollback_mb = value;
            else throw std::runtime_error("unknown PARAM: " + fields[1]);
        } else if (fields[0] == "WAVE" && fields.size() == 6) {
            result.waves.push_back({static_cast<int>(number(fields[1])), number(fields[2]), number(fields[3]),
                number(fields[4]), number(fields[5])});
        } else if (fields[0] == "PACKAGE" && fields.size() == 12) {
            if (package_index.count(fields[1])) throw std::runtime_error("duplicate package: " + fields[1]);
            int index = static_cast<int>(result.packages.size());
            package_index[fields[1]] = index;
            result.packages.push_back({fields[1], fields[2], fields[3], number(fields[4]), number(fields[5]),
                number(fields[6]), number(fields[7]), number(fields[8]), number(fields[9]), number(fields[10]),
                number(fields[11])});
        } else if (fields[0] == "DEP" && fields.size() == 3) {
            raw_deps.push_back(fields);
        } else if (fields[0] == "BRIDGE" && fields.size() == 6) {
            raw_bridges.push_back(fields);
        } else {
            throw std::runtime_error("invalid row: " + raw);
        }
    }

    if (result.wave_count <= 0 || result.max_actions <= 0 || result.max_bridge_mb <= 0 || result.max_rollback_mb <= 0) {
        throw std::runtime_error("missing or invalid PARAM rows");
    }
    if (result.packages.empty() || result.packages.size() > 63 || raw_bridges.size() > 63) {
        throw std::runtime_error("unsupported package or bridge count");
    }
    if (static_cast<int>(result.waves.size()) != result.wave_count) {
        throw std::runtime_error("wrong WAVE count");
    }
    for (int i = 0; i < result.wave_count; ++i) {
        if (result.waves[i].index != i + 1) throw std::runtime_error("WAVE rows out of order");
    }

    for (const auto& row : raw_deps) {
        if (!package_index.count(row[1]) || !package_index.count(row[2])) {
            throw std::runtime_error("DEP names unknown package");
        }
        result.deps.emplace_back(package_index[row[1]], package_index[row[2]]);
    }
    result.bridge_for_package.assign(result.packages.size(), -1);
    for (const auto& row : raw_bridges) {
        auto found = package_index.find(row[1]);
        if (found == package_index.end()) throw std::runtime_error("BRIDGE names unknown package");
        int provider = found->second;
        if (result.bridge_for_package[provider] != -1) throw std::runtime_error("duplicate BRIDGE provider");
        int bridge_index = static_cast<int>(result.bridges.size());
        result.bridge_for_package[provider] = bridge_index;
        result.bridges.push_back({provider, number(row[2]), number(row[3]), number(row[4]), number(row[5])});
    }
    return result;
}

enum class ActionType { RebuildSafe, RebuildFast, Validate, BridgeOn, BridgeOff };

struct Action {
    ActionType type;
    int package = -1;
    int bridge = -1;
    std::string id;
    i64 minutes = 0;
};

struct State {
    int wave = 0;
    u64 rebuilt = 0;
    u64 fast = 0;
    u64 validated = 0;
    u64 active = 0;
    u64 used = 0;

    bool operator==(const State& other) const {
        return wave == other.wave && rebuilt == other.rebuilt && fast == other.fast && validated == other.validated
            && active == other.active && used == other.used;
    }
};

struct StateHash {
    std::size_t operator()(const State& state) const {
        std::size_t h = std::hash<u64>{}(state.rebuilt);
        h ^= std::hash<u64>{}(state.fast + 0x13198a2e03707344ULL + (h << 6) + (h >> 2));
        h ^= std::hash<u64>{}(state.validated + 0x243f6a8885a308d3ULL + (h << 6) + (h >> 2));
        h ^= std::hash<u64>{}(state.active + 0x9e3779b97f4a7c15ULL + (h << 6) + (h >> 2));
        h ^= std::hash<u64>{}(state.used + 0x517cc1b727220a95ULL + (h << 6) + (h >> 2));
        h ^= std::hash<int>{}(state.wave + 0x45d9f3b + static_cast<int>(h));
        return h;
    }
};

struct Result {
    bool feasible = false;
    i64 migration_cost = 0;
    i64 peak_bridge_mb = 0;
    i64 peak_rollback_mb = 0;
    i64 action_minutes = 0;
    std::vector<std::vector<std::string>> schedule;
};

static bool better(const Result& left, const Result& right) {
    if (!left.feasible) return false;
    if (!right.feasible) return true;
    if (left.migration_cost != right.migration_cost) return left.migration_cost < right.migration_cost;
    if (left.peak_bridge_mb != right.peak_bridge_mb) return left.peak_bridge_mb < right.peak_bridge_mb;
    if (left.peak_rollback_mb != right.peak_rollback_mb) return left.peak_rollback_mb < right.peak_rollback_mb;
    if (left.action_minutes != right.action_minutes) return left.action_minutes < right.action_minutes;
    return left.schedule < right.schedule;
}

class Optimizer {
public:
    explicit Optimizer(Case input) : data(std::move(input)) {
        all_rebuilt = data.packages.size() == 64 ? ~u64{0} : ((u64{1} << data.packages.size()) - 1);
    }

    Result solve() {
        Result answer = visit({0, 0, 0, 0, 0, 0});
        if (!answer.feasible) throw std::runtime_error("input has no feasible migration schedule");
        return answer;
    }

private:
    Case data;
    u64 all_rebuilt = 0;
    std::unordered_map<State, Result, StateHash> memo;

    i64 bridge_storage(u64 active) const {
        i64 total = 0;
        for (std::size_t i = 0; i < data.bridges.size(); ++i) {
            if (active & (u64{1} << i)) total += data.bridges[i].storage_mb;
        }
        return total;
    }

    i64 rollback_storage(u64 rebuilt, u64 fast, u64 validated) const {
        i64 total = 0;
        for (std::size_t i = 0; i < data.packages.size(); ++i) {
            u64 bit = u64{1} << i;
            if ((rebuilt & bit) && !(validated & bit)) {
                total += (fast & bit) ? data.packages[i].fast_rollback_mb : data.packages[i].safe_rollback_mb;
            }
        }
        return total;
    }

    i64 wave_cost(int wave, u64 rebuilt, u64 fast, u64 validated, u64 active) const {
        i64 total = 0;
        for (std::size_t i = 0; i < data.packages.size(); ++i) {
            if (!(rebuilt & (u64{1} << i))) {
                total += data.waves[wave].old_multiplier * data.packages[i].old_exposure_weight;
            } else if (!(validated & (u64{1} << i))) {
                total += data.waves[wave].burnin_multiplier
                    * ((fast & (u64{1} << i)) ? data.packages[i].fast_burnin_weight
                                               : data.packages[i].safe_burnin_weight);
            }
        }
        for (std::size_t i = 0; i < data.bridges.size(); ++i) {
            if (active & (u64{1} << i)) total += data.bridges[i].carrying_cost;
        }
        return total;
    }

    bool compatible(u64 rebuilt, u64 active) const {
        for (auto [consumer, provider] : data.deps) {
            bool consumer_new = (rebuilt & (u64{1} << consumer)) != 0;
            bool provider_new = (rebuilt & (u64{1} << provider)) != 0;
            if (consumer_new == provider_new) continue;
            int bridge = data.bridge_for_package[provider];
            if (bridge < 0 || !(active & (u64{1} << bridge))) return false;
        }
        return true;
    }

    bool validation_dependencies(u64 validated) const {
        for (auto [consumer, provider] : data.deps) {
            if ((validated & (u64{1} << consumer)) && !(validated & (u64{1} << provider))) return false;
        }
        return true;
    }

    bool capacity_lower_bound(const State& state) const {
        int waves_left = data.wave_count - state.wave;
        int required_actions = static_cast<int>(data.packages.size()) - __builtin_popcountll(state.rebuilt)
            + static_cast<int>(data.packages.size()) - __builtin_popcountll(state.validated)
            + __builtin_popcountll(state.active);
        if (required_actions > waves_left * data.max_actions) return false;

        i64 required_build = 0;
        i64 required_test = 0;
        for (std::size_t i = 0; i < data.packages.size(); ++i) {
            if (!(state.rebuilt & (u64{1} << i))) {
                required_build += std::min(data.packages[i].safe_rebuild_minutes,
                    data.packages[i].fast_rebuild_minutes);
            }
            if (!(state.validated & (u64{1} << i))) required_test += data.packages[i].validate_minutes;
        }
        for (std::size_t i = 0; i < data.bridges.size(); ++i) {
            if (state.active & (u64{1} << i)) required_build += data.bridges[i].disable_minutes;
        }
        i64 available_build = 0;
        i64 available_test = 0;
        for (int i = state.wave; i < data.wave_count; ++i) {
            available_build += data.waves[i].build_minutes;
            available_test += data.waves[i].test_minutes;
        }
        return required_build <= available_build && required_test <= available_test;
    }

    std::vector<Action> available(const State& state) const {
        std::vector<Action> actions;
        for (std::size_t i = 0; i < data.packages.size(); ++i) {
            if (!(state.rebuilt & (u64{1} << i))) {
                actions.push_back({ActionType::RebuildFast, static_cast<int>(i), -1,
                    "REBUILD_FAST_" + data.packages[i].id, data.packages[i].fast_rebuild_minutes});
                actions.push_back({ActionType::RebuildSafe, static_cast<int>(i), -1,
                    "REBUILD_SAFE_" + data.packages[i].id, data.packages[i].safe_rebuild_minutes});
            } else if (!(state.validated & (u64{1} << i))) {
                actions.push_back({ActionType::Validate, static_cast<int>(i), -1,
                    "VALIDATE_" + data.packages[i].id, data.packages[i].validate_minutes});
            }
        }
        for (std::size_t i = 0; i < data.bridges.size(); ++i) {
            const auto& bridge = data.bridges[i];
            const std::string& provider = data.packages[bridge.provider].id;
            if (state.active & (u64{1} << i)) {
                actions.push_back({ActionType::BridgeOff, bridge.provider, static_cast<int>(i),
                    "BRIDGE_OFF_" + provider, bridge.disable_minutes});
            } else if (!(state.used & (u64{1} << i))) {
                actions.push_back({ActionType::BridgeOn, bridge.provider, static_cast<int>(i),
                    "BRIDGE_ON_" + provider, bridge.enable_minutes});
            }
        }
        std::sort(actions.begin(), actions.end(), [](const Action& a, const Action& b) { return a.id < b.id; });
        return actions;
    }

    Result visit(const State& state) {
        auto known = memo.find(state);
        if (known != memo.end()) return known->second;

        if (state.wave == data.wave_count) {
            Result terminal;
            terminal.feasible = state.rebuilt == all_rebuilt && state.validated == all_rebuilt && state.active == 0;
            memo.emplace(state, terminal);
            return terminal;
        }
        if (!capacity_lower_bound(state)) {
            Result impossible;
            memo.emplace(state, impossible);
            return impossible;
        }

        const auto actions = available(state);
        std::vector<int> chosen;
        Result best;

        auto evaluate = [&]() {
            i64 build_minutes = 0;
            i64 test_minutes = 0;
            u64 rebuilt = state.rebuilt;
            u64 fast = state.fast;
            u64 validated = state.validated;
            u64 active = state.active;
            u64 used = state.used;
            std::vector<std::string> ids;
            std::vector<std::string> domains;

            for (int selected : chosen) {
                const Action& action = actions[selected];
                ids.push_back(action.id);
                if (action.type == ActionType::RebuildSafe || action.type == ActionType::RebuildFast
                    || action.type == ActionType::Validate) {
                    const std::string& domain = data.packages[action.package].domain;
                    if (std::find(domains.begin(), domains.end(), domain) != domains.end()) return;
                    domains.push_back(domain);
                    if (action.type == ActionType::RebuildSafe || action.type == ActionType::RebuildFast) {
                        build_minutes += action.minutes;
                        rebuilt |= u64{1} << action.package;
                        if (action.type == ActionType::RebuildFast) fast |= u64{1} << action.package;
                    } else {
                        test_minutes += action.minutes;
                        validated |= u64{1} << action.package;
                    }
                } else if (action.type == ActionType::BridgeOn) {
                    build_minutes += action.minutes;
                    active |= u64{1} << action.bridge;
                    used |= u64{1} << action.bridge;
                } else {
                    build_minutes += action.minutes;
                    active &= ~(u64{1} << action.bridge);
                }
            }
            if (build_minutes > data.waves[state.wave].build_minutes
                || test_minutes > data.waves[state.wave].test_minutes) return;
            i64 bridge_mb = bridge_storage(active);
            i64 rollback_mb = rollback_storage(rebuilt, fast, validated);
            if (bridge_mb > data.max_bridge_mb || rollback_mb > data.max_rollback_mb
                || !compatible(rebuilt, active) || !validation_dependencies(validated)) return;

            State next{state.wave + 1, rebuilt, fast, validated, active, used};
            if (!capacity_lower_bound(next)) return;
            Result suffix = visit(next);
            if (!suffix.feasible) return;

            Result candidate;
            candidate.feasible = true;
            candidate.migration_cost = wave_cost(state.wave, rebuilt, fast, validated, active) + suffix.migration_cost;
            candidate.peak_bridge_mb = std::max(bridge_mb, suffix.peak_bridge_mb);
            candidate.peak_rollback_mb = std::max(rollback_mb, suffix.peak_rollback_mb);
            candidate.action_minutes = build_minutes + test_minutes + suffix.action_minutes;
            candidate.schedule.reserve(1 + suffix.schedule.size());
            candidate.schedule.push_back(std::move(ids));
            candidate.schedule.insert(candidate.schedule.end(), suffix.schedule.begin(), suffix.schedule.end());
            if (better(candidate, best)) best = std::move(candidate);
        };

        std::function<void(int)> enumerate = [&](int start) {
            evaluate();
            if (static_cast<int>(chosen.size()) == data.max_actions) return;
            for (int i = start; i < static_cast<int>(actions.size()); ++i) {
                chosen.push_back(i);
                enumerate(i + 1);
                chosen.pop_back();
            }
        };
        enumerate(0);
        memo.emplace(state, best);
        return best;
    }
};

static std::string json_string(const std::string& value) {
    std::string result = "\"";
    for (unsigned char ch : value) {
        if (ch == '\\' || ch == '"') {
            result.push_back('\\');
            result.push_back(static_cast<char>(ch));
        } else if (ch == '\n') result += "\\n";
        else if (ch == '\r') result += "\\r";
        else if (ch == '\t') result += "\\t";
        else result.push_back(static_cast<char>(ch));
    }
    result.push_back('"');
    return result;
}

static void json_array(std::ostream& out, const std::vector<std::string>& values) {
    out << '[';
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i) out << ',';
        out << json_string(values[i]);
    }
    out << ']';
}

static void solve_file(const std::string& input_path, const std::string& output_path) {
    Case data = parse_case(input_path);
    Result answer = Optimizer(data).solve();

    std::unordered_map<std::string, Action> action_by_id;
    for (std::size_t i = 0; i < data.packages.size(); ++i) {
        Action safe{ActionType::RebuildSafe, static_cast<int>(i), -1,
            "REBUILD_SAFE_" + data.packages[i].id, data.packages[i].safe_rebuild_minutes};
        Action fast{ActionType::RebuildFast, static_cast<int>(i), -1,
            "REBUILD_FAST_" + data.packages[i].id, data.packages[i].fast_rebuild_minutes};
        Action validate{ActionType::Validate, static_cast<int>(i), -1,
            "VALIDATE_" + data.packages[i].id, data.packages[i].validate_minutes};
        action_by_id.emplace(safe.id, safe);
        action_by_id.emplace(fast.id, fast);
        action_by_id.emplace(validate.id, validate);
    }
    for (std::size_t i = 0; i < data.bridges.size(); ++i) {
        const auto& bridge = data.bridges[i];
        const auto& provider = data.packages[bridge.provider].id;
        Action on{ActionType::BridgeOn, bridge.provider, static_cast<int>(i),
            "BRIDGE_ON_" + provider, bridge.enable_minutes};
        Action off{ActionType::BridgeOff, bridge.provider, static_cast<int>(i),
            "BRIDGE_OFF_" + provider, bridge.disable_minutes};
        action_by_id.emplace(on.id, on);
        action_by_id.emplace(off.id, off);
    }

    std::ofstream out(output_path);
    if (!out) throw std::runtime_error("cannot open output: " + output_path);
    out << "{\n";
    out << "  \"migration_cost\": " << answer.migration_cost << ",\n";
    out << "  \"peak_bridge_mb\": " << answer.peak_bridge_mb << ",\n";
    out << "  \"peak_rollback_mb\": " << answer.peak_rollback_mb << ",\n";
    out << "  \"total_action_minutes\": " << answer.action_minutes << ",\n";
    out << "  \"waves\": [\n";

    u64 rebuilt = 0;
    u64 validated = 0;
    u64 active = 0;
    for (int wave = 0; wave < data.wave_count; ++wave) {
        i64 build_minutes = 0;
        i64 test_minutes = 0;
        for (const auto& id : answer.schedule[wave]) {
            const Action& action = action_by_id.at(id);
            if (action.type == ActionType::RebuildSafe || action.type == ActionType::RebuildFast) {
                build_minutes += action.minutes;
                rebuilt |= u64{1} << action.package;
            } else if (action.type == ActionType::Validate) {
                test_minutes += action.minutes;
                validated |= u64{1} << action.package;
            } else if (action.type == ActionType::BridgeOn) {
                build_minutes += action.minutes;
                active |= u64{1} << action.bridge;
            } else {
                build_minutes += action.minutes;
                active &= ~(u64{1} << action.bridge);
            }
        }
        std::vector<std::string> active_ids;
        std::vector<std::string> old_ids;
        std::vector<std::string> awaiting_ids;
        std::vector<std::string> validated_ids;
        for (std::size_t i = 0; i < data.bridges.size(); ++i) {
            if (active & (u64{1} << i)) active_ids.push_back(data.packages[data.bridges[i].provider].id);
        }
        for (std::size_t i = 0; i < data.packages.size(); ++i) {
            u64 bit = u64{1} << i;
            if (!(rebuilt & bit)) old_ids.push_back(data.packages[i].id);
            else if (!(validated & bit)) awaiting_ids.push_back(data.packages[i].id);
            else validated_ids.push_back(data.packages[i].id);
        }
        std::sort(active_ids.begin(), active_ids.end());
        std::sort(old_ids.begin(), old_ids.end());
        std::sort(awaiting_ids.begin(), awaiting_ids.end());
        std::sort(validated_ids.begin(), validated_ids.end());
        out << "    {\"wave_index\": " << wave + 1 << ", \"action_ids\": ";
        json_array(out, answer.schedule[wave]);
        out << ", \"build_minutes\": " << build_minutes << ", \"test_minutes\": " << test_minutes
            << ", \"active_bridge_package_ids\": ";
        json_array(out, active_ids);
        out << ", \"remaining_old_package_ids\": ";
        json_array(out, old_ids);
        out << ", \"awaiting_validation_package_ids\": ";
        json_array(out, awaiting_ids);
        out << ", \"validated_package_ids\": ";
        json_array(out, validated_ids);
        out << '}';
        if (wave + 1 != data.wave_count) out << ',';
        out << '\n';
    }
    out << "  ]\n}\n";
}
