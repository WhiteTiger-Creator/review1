#include "shovehalf.hpp"

#include <cctype>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <optional>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <vector>

// The shovehalf engine. It reads the board file for the room span and the nudge, reads
// each board line into the rooms of its discs, and answers the board with the call for
// the player to move: VOID when a room is out of range, STUCK when that player cannot
// force a win, and FORCED with one winning shove when they can.

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

// parseSpan reads a span word: a run of decimal digits naming a whole number that
// fits a signed 64-bit integer. A word that is not such a run, or one too large to
// fit, is not a value.
static bool parseSpan(const std::string& w, int64_t& out) {
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

    int64_t x = 0;
    for (int64_t g : gaps) {
        x ^= g;
    }
    if (x == 0) {
        return head + "STUCK";
    }
    for (size_t i = 0; i < gaps.size(); i++) {
        int64_t g = gaps[i];
        if (g > 0) {
            int64_t t = g ^ x;
            if (t < g) {
                return head + "FORCED shove disc " + std::to_string(i + 1) +
                       " forward " + std::to_string(static_cast<long long>(g - t));
            }
        }
    }
    return head + "STUCK";
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
        if (line.rfind(lp, 0) == 0) {
            std::string w = firstWord(trim(line.substr(lp.size())));
            int64_t v;
            if (parseSpan(w, v)) {
                l.span = v;
                l.hasSpan = true;
            }
        }
        if (nl == std::string::npos) {
            break;
        }
        start = nl + 1;
    }
    return l;
}
