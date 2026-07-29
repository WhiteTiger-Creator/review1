#ifndef SHOVEHALF_HPP
#define SHOVEHALF_HPP

#include <cstdint>
#include <optional>
#include <string>

// Board holds the settings read from a board file. span is the largest room any
// one disc of the line may hold at this road, and hasSpan says whether a span was
// given. nudge is the most spaces a single disc may be shoved forward on one turn, and
// hasNudge says whether a nudge was given. The player to move is the one about to shove.
struct Board {
    int64_t span = 0;
    bool hasSpan = false;
    int64_t nudge = 0;
    bool hasNudge = false;

    // eval reads one board line and returns its output line, or no value when the
    // line is not a board at all: a line with no fields, or a line that carries a
    // field which is not a whole-number literal.
    std::optional<std::string> eval(const std::string& line) const;
};

// load reads the board file, returning no value when the file cannot be read (a
// missing path, or a path that is a directory rather than a file).
std::optional<Board> load(const std::string& path);

#endif
