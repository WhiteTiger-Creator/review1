#include "shovehalf.hpp"

#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

// shovehalf takes the path to a board file as its single command-line argument, then
// reads one board per line from standard input and prints one line per board it
// answers. The board file gives the room span and the shove nudge for this road.
// How a board is read, whether the player to move can force a win and which winning
// shove is reported are all handled by the shovehalf unit this calls into, through
// load(path) to read the board file and Board::eval(line) to score each board.
int main(int argc, char** argv) {
    std::vector<std::string> args(argv + 1, argv + argc);
    if (args.size() != 1) {
        return 2;
    }

    std::optional<Board> l = load(args[0]);
    if (!l.has_value()) {
        return 2;
    }

    std::stringstream ss;
    ss << std::cin.rdbuf();
    std::string input = ss.str();

    std::vector<std::string> out;
    size_t start = 0;
    while (start <= input.size()) {
        size_t nl = input.find('\n', start);
        std::string line = (nl == std::string::npos)
                               ? input.substr(start)
                               : input.substr(start, nl - start);
        std::optional<std::string> answer = l->eval(line);
        if (answer.has_value()) {
            out.push_back(answer.value());
        }
        if (nl == std::string::npos) {
            break;
        }
        start = nl + 1;
    }

    for (const std::string& line : out) {
        std::cout << line << "\n";
    }
    return 0;
}
