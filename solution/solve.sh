#!/bin/bash
set -euo pipefail
cat > /app/environment/src/flux_recon.cpp <<'CPP'
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace fs = std::filesystem;

struct Invalid : std::runtime_error { using std::runtime_error::runtime_error; };

struct Actor {
    std::string id;
    int row = 0;
    int col = 0;
    int energy = 0;
    int priority = 0;
    std::string status = "active";
    int bumps = 0;
    int blocks = 0;
};

struct Case {
    std::string case_id;
    int rows = 0;
    int cols = 0;
    int rounds = 0;
    std::vector<std::string> grid;
    std::map<char, std::vector<std::pair<int,int>>> portals;
    std::map<std::string, Actor> actors;
    std::map<std::string, std::vector<std::string>> commands;
};

struct ActorOut {
    std::string id;
    int row = 0, col = 0, energy = 0, bumps = 0, blocks = 0;
    std::string status;
};

struct MatchOut {
    std::string case_id;
    int rounds_completed = 0;
    std::vector<ActorOut> actors;
    std::vector<std::string> events;
    int score = 0;
    std::string digest;
};

static bool ident_ok(const std::string& s) {
    if (s.empty()) return false;
    for (char ch : s) {
        if (!(std::isalnum(static_cast<unsigned char>(ch)) || ch == '-' || ch == '_')) return false;
    }
    return true;
}

static std::vector<std::string> tokens_from_file(const fs::path& path) {
    std::ifstream in(path);
    if (!in) throw Invalid("invalid: cannot open case");
    std::vector<std::string> toks;
    std::string line;
    while (std::getline(in, line)) {
        size_t first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        if (line[first] == ';') continue;
        std::istringstream iss(line);
        std::string tok;
        while (iss >> tok) toks.push_back(tok);
    }
    return toks;
}

struct Parser {
    std::vector<std::string> toks;
    size_t idx = 0;
    explicit Parser(std::vector<std::string> t) : toks(std::move(t)) {}
    std::string need(const std::string& expected = "") {
        if (idx >= toks.size()) throw Invalid("invalid: unexpected end");
        std::string tok = toks[idx++];
        if (!expected.empty() && tok != expected) throw Invalid("invalid: expected " + expected);
        return tok;
    }
    int need_int() {
        std::string s = need();
        size_t pos = 0;
        int val = 0;
        try { val = std::stoi(s, &pos); } catch (...) { throw Invalid("invalid: bad integer"); }
        if (pos != s.size()) throw Invalid("invalid: bad integer");
        return val;
    }
};

static Case parse_case(const fs::path& path) {
    Parser p(tokens_from_file(path));
    Case c;
    p.need("case_id");
    c.case_id = p.need();
    if (!ident_ok(c.case_id)) throw Invalid("invalid: bad case id");
    p.need("rows"); c.rows = p.need_int();
    p.need("cols"); c.cols = p.need_int();
    p.need("rounds"); c.rounds = p.need_int();
    if (c.rows <= 0 || c.cols <= 0 || c.rounds <= 0) throw Invalid("invalid: bad dimensions");
    p.need("grid");
    for (int r = 0; r < c.rows; ++r) {
        std::string row = p.need();
        if (static_cast<int>(row.size()) != c.cols) throw Invalid("invalid: wrong row length");
        for (int col = 0; col < c.cols; ++col) {
            char ch = row[col];
            if (!(ch == '#' || ch == '.' || ch == 'E' || ch == 'H' || ch == '+' || ch == 'P' || ch == 'G' || ch == 'T' || std::isdigit(static_cast<unsigned char>(ch)))) {
                throw Invalid("invalid: bad grid char");
            }
            if (std::isdigit(static_cast<unsigned char>(ch))) c.portals[ch].push_back({r, col});
        }
        c.grid.push_back(row);
    }
    p.need("end_grid");
    for (const auto& kv : c.portals) {
        if (kv.second.size() != 2) throw Invalid("invalid: portal count");
    }
    p.need("actors");
    std::set<std::pair<int,int>> starts;
    while (true) {
        std::string tok = p.need();
        if (tok == "end_actors") break;
        Actor a;
        a.id = tok;
        if (!ident_ok(a.id) || c.actors.count(a.id)) throw Invalid("invalid: bad actor");
        a.row = p.need_int();
        a.col = p.need_int();
        a.energy = p.need_int();
        a.priority = p.need_int();
        if (a.row < 0 || a.row >= c.rows || a.col < 0 || a.col >= c.cols || c.grid[a.row][a.col] == '#') {
            throw Invalid("invalid: bad actor position");
        }
        if (starts.count({a.row, a.col})) throw Invalid("invalid: duplicate position");
        if (a.energy < 0 || a.energy > 9 || a.priority < 0 || a.priority > 99) throw Invalid("invalid: bad actor stats");
        starts.insert({a.row, a.col});
        c.actors[a.id] = a;
    }
    if (c.actors.empty()) throw Invalid("invalid: no actors");
    p.need("commands");
    const std::set<std::string> allowed = {"W", "N", "S", "E", "WST", "DN", "DS", "DE", "DW"};
    while (true) {
        std::string tok = p.need();
        if (tok == "end_commands") break;
        if (!c.actors.count(tok) || c.commands.count(tok)) throw Invalid("invalid: bad command actor");
        std::vector<std::string> row;
        for (int i = 0; i < c.rounds; ++i) {
            std::string cmd = p.need();
            if (!allowed.count(cmd)) throw Invalid("invalid: bad command");
            row.push_back(cmd);
        }
        c.commands[tok] = row;
    }
    if (c.commands.size() != c.actors.size()) throw Invalid("invalid: missing commands");
    if (p.idx != p.toks.size()) throw Invalid("invalid: trailing tokens");
    return c;
}

static uint64_t fnv_value(const std::vector<std::string>& tokens) {
    uint64_t h = 0xcbf29ce484222325ULL;
    for (const std::string& token : tokens) {
        for (unsigned char b : token) {
            h ^= static_cast<uint64_t>(b);
            h *= 0x100000001b3ULL;
        }
    }
    return h;
}

static std::string hex16(uint64_t h) {
    std::ostringstream oss;
    oss << std::hex << std::nouppercase << std::setfill('0') << std::setw(16) << h;
    return oss.str();
}

static std::pair<int,int> dir_for(const std::string& cmd) {
    if (cmd == "N" || cmd == "DN") return {-1, 0};
    if (cmd == "S" || cmd == "DS") return {1, 0};
    if (cmd == "E" || cmd == "DE") return {0, 1};
    if (cmd == "WST" || cmd == "DW") return {0, -1};
    return {0, 0};
}

static std::tuple<int,int,char> portal_target(const Case& c, int r, int col) {
    char ch = c.grid[r][col];
    if (!std::isdigit(static_cast<unsigned char>(ch))) return {r, col, '\0'};
    const auto& cells = c.portals.at(ch);
    auto target = (cells[0] == std::make_pair(r, col)) ? cells[1] : cells[0];
    return {target.first, target.second, ch};
}

static bool turret_hits(const Case& c, int row, int col, bool gates_open) {
    const int dirs[4][2] = {{-1,0},{1,0},{0,-1},{0,1}};
    for (const auto& d : dirs) {
        int r = row + d[0], cc = col + d[1];
        while (r >= 0 && r < c.rows && cc >= 0 && cc < c.cols) {
            char tile = c.grid[r][cc];
            if (tile == '#' || (tile == 'G' && !gates_open)) break;
            if (tile == 'T') return true;
            r += d[0]; cc += d[1];
        }
    }
    return false;
}

static MatchOut simulate_case(const Case& c, int max_rounds) {
    std::map<std::string, Actor> actors = c.actors;
    int rounds = c.rounds;
    if (max_rounds > 0) rounds = std::min(rounds, max_rounds);
    std::set<std::pair<int,int>> echoes;
    std::vector<std::string> events;
    bool gates_open = false;

    for (int rnd = 0; rnd < rounds; ++rnd) {
        std::vector<std::string> active_ids;
        for (const auto& kv : actors) if (kv.second.status == "active") active_ids.push_back(kv.first);
        std::map<std::string, std::pair<int,int>> proposals;
        std::map<std::string, int> costs;
        std::set<std::string> blocked_initial;
        for (const std::string& aid : active_ids) {
            Actor& a = actors[aid];
            std::string cmd = c.commands.at(aid)[rnd];
            int cost = (cmd == "W") ? 0 : ((cmd.size() == 2 && cmd[0] == 'D') ? 2 : 1);
            if (a.energy < cost) {
                events.push_back("r" + std::to_string(rnd) + ":" + aid + ":tired");
                proposals[aid] = {a.row, a.col}; costs[aid] = 0; continue;
            }
            if (cmd == "W") {
                proposals[aid] = {a.row, a.col}; costs[aid] = 0; continue;
            }
            auto [dr, dc] = dir_for(cmd);
            int steps = (cmd.size() == 2 && cmd[0] == 'D') ? 2 : 1;
            int cr = a.row, cc = a.col;
            bool failed = false;
            for (int step = 0; step < steps; ++step) {
                int nr = cr + dr, nc = cc + dc;
                if (nr < 0 || nr >= c.rows || nc < 0 || nc >= c.cols || c.grid[nr][nc] == '#') {
                    events.push_back("r" + std::to_string(rnd) + ":" + aid + ":wall");
                    failed = true; break;
                }
                if (c.grid[nr][nc] == 'G' && !gates_open) {
                    events.push_back("r" + std::to_string(rnd) + ":" + aid + ":gate");
                    failed = true; break;
                }
                if (echoes.count({nr, nc})) {
                    events.push_back("r" + std::to_string(rnd) + ":" + aid + ":echo");
                    failed = true; break;
                }
                cr = nr; cc = nc;
                auto [pr, pc, digit] = portal_target(c, cr, cc);
                if (digit != '\0') {
                    cr = pr; cc = pc;
                    events.push_back("r" + std::to_string(rnd) + ":" + aid + ":portal:" + std::string(1, digit));
                }
            }
            if (failed) {
                proposals[aid] = {a.row, a.col}; costs[aid] = 0; blocked_initial.insert(aid);
            } else {
                proposals[aid] = {cr, cc}; costs[aid] = cost;
            }
        }
        std::set<std::string> accepted;
        for (const std::string& aid : active_ids) {
            Actor& a = actors[aid];
            if (proposals[aid] != std::make_pair(a.row, a.col)) accepted.insert(aid);
        }
        std::map<std::pair<int,int>, std::vector<std::string>> dest_to_ids;
        for (const std::string& aid : accepted) dest_to_ids[proposals[aid]].push_back(aid);
        for (auto& kv : dest_to_ids) {
            auto ids = kv.second;
            std::sort(ids.begin(), ids.end());
            if (ids.size() > 1) {
                std::string winner = ids[0];
                for (const std::string& id : ids) {
                    if (std::make_pair(actors[id].priority, id) < std::make_pair(actors[winner].priority, winner)) winner = id;
                }
                for (const std::string& id : ids) {
                    if (id != winner) {
                        accepted.erase(id);
                        actors[id].bumps += 1;
                        events.push_back("r" + std::to_string(rnd) + ":" + id + ":bump:" + winner);
                    }
                }
            }
        }
        bool changed = true;
        while (changed) {
            changed = false;
            std::map<std::pair<int,int>, std::string> occupied_by;
            for (const std::string& aid : active_ids) occupied_by[{actors[aid].row, actors[aid].col}] = aid;
            std::vector<std::string> acc_ids(accepted.begin(), accepted.end());
            std::sort(acc_ids.begin(), acc_ids.end());
            for (const std::string& aid : acc_ids) {
                auto dest = proposals[aid];
                auto it = occupied_by.find(dest);
                if (it == occupied_by.end() || it->second == aid) continue;
                const std::string occupant = it->second;
                bool direct_swap = accepted.count(occupant) && proposals[occupant] == std::make_pair(actors[aid].row, actors[aid].col);
                if (direct_swap) continue;
                if (!accepted.count(occupant)) {
                    accepted.erase(aid);
                    actors[aid].blocks += 1;
                    events.push_back("r" + std::to_string(rnd) + ":" + aid + ":blocked:" + occupant);
                    changed = true;
                    break;
                }
            }
        }
        std::set<std::pair<int,int>> next_echoes;
        for (const std::string& aid : active_ids) {
            Actor& a = actors[aid];
            auto start = std::make_pair(a.row, a.col);
            if (accepted.count(aid)) {
                a.row = proposals[aid].first; a.col = proposals[aid].second;
                a.energy -= costs[aid];
                if (start != proposals[aid]) next_echoes.insert(start);
            } else if (costs[aid] == 0 && proposals[aid] == start && !blocked_initial.count(aid)) {
                a.energy = std::min(9, a.energy + 1);
            }
        }
        for (const std::string& aid : active_ids) {
            Actor& a = actors[aid];
            if (a.status != "active") continue;
            char tile = c.grid[a.row][a.col];
            if (tile == 'H') {
                a.energy -= 1;
                events.push_back("r" + std::to_string(rnd) + ":" + aid + ":hazard");
            }
            if (tile == '+') {
                int before = a.energy;
                a.energy = std::min(9, a.energy + 2);
                if (a.energy != before) events.push_back("r" + std::to_string(rnd) + ":" + aid + ":charge");
            }
            if (a.energy < 0) {
                a.status = "down";
                events.push_back("r" + std::to_string(rnd) + ":" + aid + ":down");
            }
        }
        bool open_now = false;
        if (!gates_open) {
            for (const std::string& aid : active_ids) {
                const Actor& a = actors[aid];
                if (a.status == "active" && c.grid[a.row][a.col] == 'P') { open_now = true; break; }
            }
        }
        if (open_now) {
            gates_open = true;
            events.push_back("r" + std::to_string(rnd) + ":arena:gate_open");
        }
        for (const std::string& aid : active_ids) {
            Actor& a = actors[aid];
            if (a.status != "active") continue;
            if (turret_hits(c, a.row, a.col, gates_open)) {
                a.energy -= 2;
                events.push_back("r" + std::to_string(rnd) + ":" + aid + ":laser");
                if (a.energy < 0) {
                    a.status = "down";
                    events.push_back("r" + std::to_string(rnd) + ":" + aid + ":down");
                }
            }
        }
        for (const std::string& aid : active_ids) {
            Actor& a = actors[aid];
            if (a.status == "active" && c.grid[a.row][a.col] == 'E') {
                a.status = "exited";
                events.push_back("r" + std::to_string(rnd) + ":" + aid + ":exit");
            }
        }
        echoes = next_echoes;
    }

    MatchOut out;
    out.case_id = c.case_id;
    out.rounds_completed = rounds;
    for (const auto& kv : actors) {
        const Actor& a = kv.second;
        out.actors.push_back({a.id, a.row, a.col, a.energy, a.bumps, a.blocks, a.status});
    }
    out.events = events;
    int score = 0;
    for (const auto& a : out.actors) {
        if (a.status == "exited") score += 100;
        if (a.status == "down") score -= 40;
        else score += 5 * a.energy;
        score -= 7 * a.bumps;
        score -= 3 * a.blocks;
    }
    out.score = score;
    std::vector<std::string> toks;
    toks.push_back("case:" + out.case_id);
    toks.push_back("rounds:" + std::to_string(out.rounds_completed));
    for (const auto& a : out.actors) {
        toks.push_back("actor:" + a.id + ":" + std::to_string(a.row) + ":" + std::to_string(a.col) + ":" + std::to_string(a.energy) + ":" + a.status + ":" + std::to_string(a.bumps) + ":" + std::to_string(a.blocks));
    }
    for (const auto& e : out.events) toks.push_back("event:" + e);
    toks.push_back("score:" + std::to_string(out.score));
    out.digest = hex16(fnv_value(toks));
    return out;
}

static std::string esc(const std::string& s) {
    std::string out;
    for (char ch : s) {
        if (ch == '\\' || ch == '"') { out.push_back('\\'); out.push_back(ch); }
        else out.push_back(ch);
    }
    return out;
}

static void write_json(const std::vector<MatchOut>& matches, const fs::path& out_path) {
    int total_score = 0, exited = 0, down = 0;
    for (const auto& m : matches) {
        total_score += m.score;
        for (const auto& a : m.actors) {
            if (a.status == "exited") exited++;
            if (a.status == "down") down++;
        }
    }
    std::vector<std::string> toks;
    for (const auto& m : matches) toks.push_back("match:" + m.case_id + ":" + m.digest + ":" + std::to_string(m.score));
    toks.push_back("counts:" + std::to_string(matches.size()) + ":" + std::to_string(total_score) + ":" + std::to_string(exited) + ":" + std::to_string(down));
    std::string summary_digest = hex16(fnv_value(toks));

    fs::create_directories(out_path.parent_path());
    std::ofstream out(out_path);
    if (!out) throw Invalid("invalid: cannot write output");
    out << "{\"matches\":[";
    for (size_t i = 0; i < matches.size(); ++i) {
        if (i) out << ",";
        const auto& m = matches[i];
        out << "{\"case_id\":\"" << esc(m.case_id) << "\",\"rounds_completed\":" << m.rounds_completed << ",\"actors\":[";
        for (size_t j = 0; j < m.actors.size(); ++j) {
            if (j) out << ",";
            const auto& a = m.actors[j];
            out << "{\"id\":\"" << esc(a.id) << "\",\"row\":" << a.row << ",\"col\":" << a.col << ",\"energy\":" << a.energy << ",\"status\":\"" << a.status << "\",\"bumps\":" << a.bumps << ",\"blocks\":" << a.blocks << "}";
        }
        out << "],\"events\":[";
        for (size_t j = 0; j < m.events.size(); ++j) {
            if (j) out << ",";
            out << "\"" << esc(m.events[j]) << "\"";
        }
        out << "],\"score\":" << m.score << ",\"digest\":\"" << m.digest << "\"}";
    }
    out << "],\"summary\":{\"match_count\":" << matches.size() << ",\"total_score\":" << total_score << ",\"exited_count\":" << exited << ",\"down_count\":" << down << ",\"digest\":\"" << summary_digest << "\"}}\n";
}

int main(int argc, char** argv) {
    std::string case_dir = "/app/environment/cases";
    std::string out_path = "/app/output/flux_report.json";
    int max_rounds = -1;
    try {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            if (arg == "--case-dir") { if (++i >= argc) throw Invalid("invalid: missing case-dir"); case_dir = argv[i]; }
            else if (arg == "--out") { if (++i >= argc) throw Invalid("invalid: missing out"); out_path = argv[i]; }
            else if (arg == "--max-rounds") {
                if (++i >= argc) throw Invalid("invalid: missing max-rounds");
                size_t pos = 0; max_rounds = std::stoi(argv[i], &pos);
                if (pos != std::string(argv[i]).size() || max_rounds <= 0) throw Invalid("invalid: bad max-rounds");
            } else throw Invalid("invalid: unknown option");
        }
        std::vector<Case> cases;
        if (!fs::exists(case_dir) || !fs::is_directory(case_dir)) throw Invalid("invalid: case dir");
        for (const auto& entry : fs::directory_iterator(case_dir)) {
            if (entry.path().extension() == ".flux") cases.push_back(parse_case(entry.path()));
        }
        if (cases.empty()) throw Invalid("invalid: no cases");
        std::sort(cases.begin(), cases.end(), [](const Case& a, const Case& b){ return a.case_id < b.case_id; });
        std::vector<MatchOut> matches;
        for (const auto& c : cases) matches.push_back(simulate_case(c, max_rounds));
        write_json(matches, out_path);
        return 0;
    } catch (const std::exception& ex) {
        std::error_code ec;
        fs::remove(out_path, ec);
        std::cerr << ex.what() << "\n";
        return 2;
    }
}
CPP
