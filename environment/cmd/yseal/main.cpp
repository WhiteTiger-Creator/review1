#include "io_glue/io_glue.hpp"

#include <iostream>
#include <string>

namespace {

int recover_live(const std::string& a, const std::string& b) {
  return io_glue::run_yseal(a, b);
}

}  // namespace

int main(int argc, char** argv) {
  std::string a;
  std::string b;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string k = argv[i];
    if (k == "--journal") {
      a = argv[i + 1];
    }
    if (k == "--report") {
      b = argv[i + 1];
    }
  }
  if (a.empty() || b.empty()) {
    std::cerr << "usage: yseal --journal <path> --report <path>\n";
    return 2;
  }
  return recover_live(a, b);
}
