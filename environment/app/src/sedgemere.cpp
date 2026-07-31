// The sedgemere level book.
//
// Nothing here learns anything yet: every reading comes back with the same
// level, which is a long way off for most of them. The readings, the two data
// files, and how this is run and scored are all in ../docs/BRIEF.md.
#include <fstream>
#include <string>

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::ifstream ask(argv[1]);
    std::ofstream out(argv[2]);
    std::string line;
    bool first = true;
    while (std::getline(ask, line)) {
        if (line.empty()) continue;
        if (first) { first = false; continue; }
        out << "0.000000\n";
    }
    return 0;
}
