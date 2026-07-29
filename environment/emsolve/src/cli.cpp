#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

#include "emsolve/assembly.hpp"
#include "emsolve/checkpoint.hpp"
#include "emsolve/diagnostics.hpp"
#include "emsolve/eigensolver.hpp"
#include "emsolve/mesh.hpp"
#include "emsolve/modes.hpp"
#include "emsolve/topology.hpp"

namespace emsolve {

bool write_modes_json(const std::string& path, const ModesOutput& output);

namespace {

static void log_line(const std::string& msg) {
  try {
    std::filesystem::create_directories("/logs/emsolve");
    std::ofstream log("/logs/emsolve/run.log", std::ios::app);
    if (log) log << msg << '\n';
  } catch (const std::exception&) {
  }
}

static void print_usage() {
  std::cout << "usage: emsolve --mesh <path> --modes <N> --output <json>\n"
            << "       [--config <toml>] [--checkpoint <path>] [--checkpoint-after <iterations>]\n"
            << "       [--resume <checkpoint>]\n";
}

static bool starts_with(const std::string& s, const std::string& prefix) {
  return s.size() >= prefix.size() && s.compare(0, prefix.size(), prefix) == 0;
}

static double parse_toml_value(const std::string& text, const std::string& section,
                               const std::string& key, double fallback) {
  std::istringstream in(text);
  std::string line;
  bool in_section = section.empty();
  while (std::getline(in, line)) {
    if (!line.empty() && line[0] == '#') continue;
    if (line.front() == '[' && line.back() == ']') {
      in_section = (line.substr(1, line.size() - 2) == section);
      continue;
    }
    if (!in_section) continue;
    const auto eq = line.find('=');
    if (eq == std::string::npos) continue;
    std::string k = line.substr(0, eq);
    while (!k.empty() && std::isspace(static_cast<unsigned char>(k.front()))) k.erase(k.begin());
    while (!k.empty() && std::isspace(static_cast<unsigned char>(k.back()))) k.pop_back();
    if (k != key) continue;
    std::string v = line.substr(eq + 1);
    while (!v.empty() && std::isspace(static_cast<unsigned char>(v.front()))) v.erase(v.begin());
    return std::stod(v);
  }
  return fallback;
}

static SolverConfig load_config(const std::string& path, int requested_modes) {
  SolverConfig cfg;
  cfg.requested_modes = requested_modes;
  if (path.empty()) return cfg;

  std::ifstream in(path);
  if (!in) throw std::runtime_error("cannot open config: " + path);
  std::ostringstream oss;
  oss << in.rdbuf();
  const std::string text = oss.str();

  cfg.max_iterations = static_cast<int>(parse_toml_value(text, "max_iterations", "value", cfg.max_iterations));
  cfg.tolerance = parse_toml_value(text, "tolerances", "algebraic", cfg.tolerance);
  return cfg;
}

}  // namespace

}  // namespace emsolve

int main(int argc, char** argv) {
  using namespace emsolve;

  std::string mesh_path;
  std::string output_path;
  std::string config_path;
  std::string checkpoint_path;
  std::string resume_path;
  int modes = 0;
  int checkpoint_after = 0;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--help" || arg == "-h") {
      print_usage();
      return 0;
    }
    if (arg == "--mesh" && i + 1 < argc) {
      mesh_path = argv[++i];
      continue;
    }
    if (arg == "--modes" && i + 1 < argc) {
      modes = std::stoi(argv[++i]);
      continue;
    }
    if (arg == "--output" && i + 1 < argc) {
      output_path = argv[++i];
      continue;
    }
    if (arg == "--config" && i + 1 < argc) {
      config_path = argv[++i];
      continue;
    }
    if (arg == "--checkpoint" && i + 1 < argc) {
      checkpoint_path = argv[++i];
      continue;
    }
    if (arg == "--checkpoint-after" && i + 1 < argc) {
      checkpoint_after = std::stoi(argv[++i]);
      continue;
    }
    if (arg == "--resume" && i + 1 < argc) {
      resume_path = argv[++i];
      continue;
    }
    std::cerr << "unknown argument: " << arg << '\n';
    print_usage();
    return 2;
  }

  if (mesh_path.empty() || output_path.empty() || modes <= 0) {
    print_usage();
    return 2;
  }

  try {
    SolverConfig cfg = load_config(config_path, modes);
    cfg.checkpoint_path = checkpoint_path;
    cfg.checkpoint_after = checkpoint_after;
    cfg.resume = !resume_path.empty();
    cfg.resume_path = resume_path;

    log_line("loading mesh: " + mesh_path);
    const Mesh mesh = Mesh::load(mesh_path);
    const Topology topo = Topology::build(mesh);
    const OperatorPair ops = assemble_operators(mesh, topo);

    log_line("active_dofs=" + std::to_string(topo.num_active_dofs));
    const SolverResult solved = solve_generalized(mesh, topo, ops, cfg);
    const auto diags =
        compute_all_diagnostics(mesh, topo, ops, solved.eigenvalues, solved.eigenvectors);

    ModesOutput output = prepare_modes(modes, solved.eigenvalues, solved.eigenvectors, diags,
                                       solved.cluster_ids.empty() ? nullptr : &solved.cluster_ids);
    output.mesh_path = mesh_path;
    output.active_dofs = topo.num_active_dofs;
    output.iterations = solved.iterations;

    if (!write_modes_json(output_path, output)) {
      throw std::runtime_error("failed to write output: " + output_path);
    }

    log_line("wrote modes to " + output_path);
    return 0;
  } catch (const std::exception& ex) {
    log_line(std::string("error: ") + ex.what());
    std::cerr << ex.what() << '\n';
    return 1;
  }
}
