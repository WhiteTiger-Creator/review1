#pragma once

#include "../core/types.hpp"

#include <string>
#include <vector>

namespace stor_io {

std::string gen_group_name(int id);
int layout_family(const std::string& path);
int list_gen_ids(const std::string& path, std::vector<int>& ids);
int read_gen_meta(const std::string& path, const std::string& group_path, GenRec& out);
int read_rank_block(const std::string& path, const GenRec& gen, int rank, std::vector<double>& owned,
                    std::vector<double>& glo, std::vector<double>& ghi, std::vector<int>& gids);
int read_hist(const std::string& path, const GenRec& gen, HistRec& out);
int read_ctrl(const std::string& path, const GenRec& gen, CtrlState& out);
int write_gen_begin(const std::string& path, int gen_id, int step, int nproc, int layout_ver,
                    const std::string& fingerprint);
int write_rank_block(const std::string& path, int gen_id, int rank, const std::vector<double>& owned,
                     const std::vector<double>& glo, const std::vector<double>& ghi,
                     const std::vector<int>& gids);
int write_hist_ctrl(const std::string& path, int gen_id, int layout_ver, const HistRec& hist,
                    const CtrlState& ctrl, double field_cksum);
int write_commit(const std::string& path, int gen_id, int committed);
int open_flags_for_input();
bool name_exists(const std::string& path, const std::string& obj);
std::string failpoint_token();
bool failpoint_is(const char* key);
int failpoint_rank();

}  // namespace stor_io
