#!/bin/bash
set -euo pipefail
cd /app

# Get the lay of the land first.
ls -R /app

# What is being asked.
cat /app/instruction.md 2>/dev/null || true

# The contract. This is the part that actually decides the answer, so read it
# properly rather than guessing the variant from memory.
cat /app/docs/rules.md

# What the engine looks like right now.
cat /app/main.cpp
cat /app/shovehalf.hpp
cat /app/shovehalf.cpp

# A sample board and some sample positions to try things against.
cat /app/fixtures/board.txt
cat /app/fixtures/positions.txt

# See the current behaviour before touching anything. The sketch exclusive-ors every
# room as if each disc were its own heap and it never reads the nudge line at all,
# so it calls the close boards backwards and, under a nudge, misses that a disc can be
# crawled only a little at a time.
g++ -O2 -std=c++17 /app/main.cpp /app/shovehalf.cpp -o /tmp/shovehalf
/tmp/shovehalf /app/fixtures/board.txt < /app/fixtures/positions.txt || true

# The board-file reading and the input reading are fine as they stand. What is wrong is
# the call and the shove. Shoving a disc forward feeds its distance to the disc behind
# it, so a board plays as a staircase whose sink is the back of the road: only every
# other room, counted from the back disc, bears on best play, so the live discs are
# the ones whose index shares the back disc's parity. A road that sets a nudge caps a
# shove, which turns each room into its residue against a full stride of nudge-plus-
# one, so a room that is a whole number of strides bears nothing; add the nudge
# line to the board-file reading and fold it in that way. Exclusive-or the bearing
# rooms of the live discs; the player to move loses on nought and wins otherwise. A
# winning shove drops one live disc's bearing to cancel the exclusive-or, which is a shove
# no farther than the nudge and no farther than the room, and a front disc shoved
# its whole room scores at the ledge.
cat > shovehalf.cpp << 'EOF'
#include "shovehalf.hpp"

#include <cctype>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <optional>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <vector>

// The shovehalf engine. It reads the board file (the room span and the shove
// nudge), reads each board into its disc rooms, and settles the board by naming the
// outcome for the player to move: shoving a disc feeds the disc behind it, so a board is
// staircase play and only every other room from the back bears, and a nudge caps a
// shove to the room's residue against a full stride. The exclusive-or of the
// bearing rooms of the live discs loses on nought and wins otherwise, and a win is
// answered with one legal winning shove.

// trim strips leading and trailing whitespace from a line.
static std::string trim(const std::string& s) {
    size_t a = 0, b = s.size();
    while (a < b && std::isspace(static_cast<unsigned char>(s[a]))) {
        a++;
    }
    while (b > a && std::isspace(static_cast<unsigned char>(s[b - 1]))) {
        b--;
    }
    return s.substr(a, b - a);
}

// firstWord returns the run of characters up to the first space or tab.
static std::string firstWord(const std::string& s) {
    size_t k = s.find_first_of(" \t");
    if (k != std::string::npos) {
        return s.substr(0, k);
    }
    return s;
}

// allDigits reports whether s is a non-empty run of decimal digits.
static bool allDigits(const std::string& s) {
    if (s.empty()) {
        return false;
    }
    for (char c : s) {
        if (c < '0' || c > '9') {
            return false;
        }
    }
    return true;
}

// parseNonNeg reads a span or nudge word: a run of decimal digits naming a whole
// number nought or more that fits a signed 64-bit integer. A word that is not such a
// run, or one too large to fit, is not a value and leaves the setting where it stood.
static bool parseNonNeg(const std::string& w, int64_t& out) {
    if (!allDigits(w)) {
        return false;
    }
    errno = 0;
    char* end = nullptr;
    long long v = std::strtoll(w.c_str(), &end, 10);
    if (errno == ERANGE || end != w.c_str() + w.size()) {
        return false;
    }
    out = static_cast<int64_t>(v);
    return true;
}

// isIntLiteral reports whether s is a whole-number literal: an optional single leading
// plus or minus sign followed by one or more decimal digits, and nothing else.
static bool isIntLiteral(const std::string& s) {
    if (s.empty()) {
        return false;
    }
    size_t i = 0;
    if (s[0] == '+' || s[0] == '-') {
        i = 1;
    }
    if (i == s.size()) {
        return false;
    }
    for (; i < s.size(); i++) {
        if (s[i] < '0' || s[i] > '9') {
            return false;
        }
    }
    return true;
}

// parseI64 reports whether s is a whole-number literal that fits a signed 64-bit
// integer, and if so returns its value. A run of digits too large to fit does not
// count as a literal.
static bool parseI64(const std::string& s, int64_t& out) {
    if (!isIntLiteral(s)) {
        return false;
    }
    errno = 0;
    char* end = nullptr;
    long long v = std::strtoll(s.c_str(), &end, 10);
    if (errno == ERANGE || end != s.c_str() + s.size()) {
        return false;
    }
    out = static_cast<int64_t>(v);
    return true;
}

// fields splits a line on runs of whitespace, dropping empty pieces.
static std::vector<std::string> fields(const std::string& s) {
    std::vector<std::string> out;
    size_t i = 0, n = s.size();
    while (i < n) {
        while (i < n && std::isspace(static_cast<unsigned char>(s[i]))) {
            i++;
        }
        if (i >= n) {
            break;
        }
        size_t j = i;
        while (j < n && !std::isspace(static_cast<unsigned char>(s[j]))) {
            j++;
        }
        out.push_back(s.substr(i, j - i));
        i = j;
    }
    return out;
}

// live reports whether the disc at 0-based position idx, in a line of n discs, bears on
// best play. Shoving a disc forward feeds its distance to the disc behind it, so the
// line reads as a staircase whose sink is the back of the road: only every other
// room, counted from the back disc, bears. In ledge order this is the position idx
// whose parity matches that of the back disc, n-1.
static bool live(size_t idx, size_t n) {
    return idx % 2 == (n - 1) % 2;
}

// bearing is the amount of disc g's room that bears on best play. With no nudge
// there is no cap on a shove and the whole room bears. With a nudge, a disc crawls
// forward at most that many spaces a turn, so its room bears only to the residue
// it leaves against a full stride of nudge-plus-one; a room that is a whole number
// of full strides bears nothing.
static int64_t bearing(int64_t g, bool hasNudge, int64_t nudge) {
    if (!hasNudge) {
        return g;
    }
    if (nudge == std::numeric_limits<int64_t>::max()) {
        // A nudge at the very top of the range is wider than any room can be, so
        // the whole room bears; guarding here keeps the stride from overflowing.
        return g;
    }
    int64_t m = nudge + 1;
    return g % m;
}

// weigh folds the bearing rooms of the live discs into one number. The player to
// move loses exactly when this is nought.
static int64_t weigh(const std::vector<int64_t>& gaps, bool hasNudge, int64_t nudge) {
    size_t n = gaps.size();
    int64_t x = 0;
    for (size_t i = 0; i < n; i++) {
        if (live(i, n)) {
            x ^= bearing(gaps[i], hasNudge, nudge);
        }
    }
    return x;
}

// winningRoll names one shove that leaves the other player a board whose reckoning is
// nought. The board passed in is a win, so such a shove exists. It brings one live disc's
// bearing down to match the rest by shoving that disc forward; the shove never exceeds
// the nudge, and a front disc shoved its whole room scores at the ledge.
static std::string winningRoll(const std::vector<int64_t>& gaps, int64_t x,
                               bool hasNudge, int64_t nudge) {
    size_t n = gaps.size();
    for (size_t i = 0; i < n; i++) {
        if (!live(i, n)) {
            continue;
        }
        int64_t a = bearing(gaps[i], hasNudge, nudge);
        int64_t t = a ^ x;
        if (t < a) {
            return "shove disc " + std::to_string(i + 1) + " forward " +
                   std::to_string(static_cast<long long>(a - t));
        }
    }
    return "";
}

std::optional<std::string> Board::eval(const std::string& line) const {
    std::vector<std::string> fs = fields(line);
    if (fs.empty()) {
        return std::nullopt;
    }
    std::vector<int64_t> gaps(fs.size());
    for (size_t i = 0; i < fs.size(); i++) {
        int64_t v;
        if (!parseI64(fs[i], v)) {
            return std::nullopt;
        }
        gaps[i] = v;
    }

    std::string head;
    bool inRange = true;
    for (size_t i = 0; i < gaps.size(); i++) {
        if (i) {
            head += " ";
        }
        head += std::to_string(static_cast<long long>(gaps[i]));
        if (gaps[i] < 0 || (hasSpan && gaps[i] > span)) {
            inRange = false;
        }
    }
    head += " | ";

    if (!inRange) {
        return head + "VOID";
    }

    int64_t x = weigh(gaps, hasNudge, nudge);
    if (x == 0) {
        return head + "STUCK";
    }
    return head + "FORCED " + winningRoll(gaps, x, hasNudge, nudge);
}

std::optional<Board> load(const std::string& path) {
    struct stat st;
    if (stat(path.c_str(), &st) != 0 || S_ISDIR(st.st_mode)) {
        return std::nullopt;
    }
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        return std::nullopt;
    }
    std::stringstream ss;
    ss << f.rdbuf();
    std::string data = ss.str();

    Board l;
    size_t start = 0;
    while (true) {
        size_t nl = data.find('\n', start);
        std::string raw = (nl == std::string::npos)
                              ? data.substr(start)
                              : data.substr(start, nl - start);
        std::string line = raw;
        size_t hash = line.find('#');
        if (hash != std::string::npos) {
            line = line.substr(0, hash);
        }
        line = trim(line);
        const std::string lp = "span:";
        const std::string sp = "nudge:";
        if (line.rfind(lp, 0) == 0) {
            std::string w = firstWord(trim(line.substr(lp.size())));
            int64_t v;
            if (parseNonNeg(w, v)) {
                l.span = v;
                l.hasSpan = true;
            }
        } else if (line.rfind(sp, 0) == 0) {
            std::string w = firstWord(trim(line.substr(sp.size())));
            int64_t v;
            if (parseNonNeg(w, v)) {
                l.nudge = v;
                l.hasNudge = true;
            }
        }
        if (nl == std::string::npos) {
            break;
        }
        start = nl + 1;
    }
    return l;
}
EOF

# Sanity check: still builds, and the probe positions now read the way the rules say.
g++ -O2 -std=c++17 /app/main.cpp /app/shovehalf.cpp -o /tmp/shovehalf
/tmp/shovehalf /app/fixtures/board.txt < /app/fixtures/positions.txt
