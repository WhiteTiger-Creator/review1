#include <fstream>
#include <iomanip>
#include <sstream>

#include "emsolve/modes.hpp"

namespace emsolve {

static void write_json_string(std::ostream& out, const std::string& s) {
  out << '"';
  for (char c : s) {
    if (c == '"') out << "\\\"";
    else if (c == '\\') out << "\\\\";
    else out << c;
  }
  out << '"';
}

bool write_modes_json(const std::string& path, const ModesOutput& output) {
  std::ofstream out(path);
  if (!out) return false;
  out << std::setprecision(16);
  out << "{\n";
  out << "  \"requested_modes\": " << output.requested << ",\n";
  out << "  \"computed_modes\": " << output.computed << ",\n";
  out << "  \"active_dofs\": " << output.active_dofs << ",\n";
  out << "  \"iterations\": " << output.iterations << ",\n";
  out << "  \"mesh\": ";
  write_json_string(out, output.mesh_path);
  out << ",\n";
  out << "  \"modes\": [\n";
  for (size_t i = 0; i < output.modes.size(); ++i) {
    const auto& m = output.modes[i];
    out << "    {\n";
    out << "      \"index\": " << m.index << ",\n";
    out << "      \"eigenvalue\": " << m.eigenvalue << ",\n";
    out << "      \"cluster_id\": " << m.cluster_id << ",\n";
    out << "      \"residuals\": {\n";
    out << "        \"algebraic\": " << m.diagnostics.algebraic_residual << ",\n";
    out << "        \"boundary_trace\": " << m.diagnostics.boundary_trace << ",\n";
    out << "        \"divergence\": " << m.diagnostics.divergence << "\n";
    out << "      },\n";
    out << "      \"coefficients\": [";
    for (size_t c = 0; c < m.coefficients.size(); ++c) {
      if (c) out << ", ";
      out << m.coefficients[c];
    }
    out << "]\n";
    out << "    }";
    if (i + 1 < output.modes.size()) out << ",";
    out << "\n";
  }
  out << "  ]\n";
  out << "}\n";
  return true;
}

}  // namespace emsolve
