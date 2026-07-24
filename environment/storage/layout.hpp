#pragma once

#include "../core/types.hpp"

#include <string>
#include <vector>

namespace stor_layout {

int detect(const std::string& path);
std::string group_for_id(const std::string& path, int id);
int load_meta(const std::string& path, int id, GenRec& out);
int load_rank(const std::string& path, const GenRec& gen, int rank, std::vector<double>& owned,
              std::vector<double>& glo, std::vector<double>& ghi, std::vector<int>& gids);
int load_hist_ctrl(const std::string& path, const GenRec& gen, HistRec& hist, CtrlState& ctrl);

}  // namespace stor_layout
