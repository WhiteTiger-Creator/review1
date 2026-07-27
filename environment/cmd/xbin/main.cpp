#include "io_glue/io_glue.hpp"

#include <iostream>
#include <string>

int main(int argc, char** argv) {
  std::string a;
  std::string b;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string k = argv[i];
    if (k == "--pair") a = argv[i + 1];
    if (k == "--journal") b = argv[i + 1];
  }
  if (a.empty() || b.empty()) {
    std::cerr << "usage: layer_emit --pair <path> --journal <path>\n";
    return 2;
  }
  return io_glue::run_emit(a, b);
}
