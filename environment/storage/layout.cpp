#include "layout.hpp"

#include "io.hpp"

#include <cstdio>
#include <string>
#include <vector>

namespace stor_layout {

int detect(const std::string& path) { return stor_io::layout_family(path); }

std::string group_for_id(const std::string& path, int id) {
    const int fam = detect(path);
    if (fam == 1) {
        std::vector<int> ids;
        stor_io::list_gen_ids(path, ids);
        if (ids.size() == 1 && ids[0] == id && !stor_io::name_exists(path, "/" + stor_io::gen_group_name(id))) {
            return "/";
        }
    }
    return std::string("/") + stor_io::gen_group_name(id);
}

int load_meta(const std::string& path, int id, GenRec& out) {
    const std::string gp = group_for_id(path, id);
    return stor_io::read_gen_meta(path, gp, out);
}

int load_rank(const std::string& path, const GenRec& gen, int rank, std::vector<double>& owned,
              std::vector<double>& glo, std::vector<double>& ghi, std::vector<int>& gids) {
    return stor_io::read_rank_block(path, gen, rank, owned, glo, ghi, gids);
}

int load_hist_ctrl(const std::string& path, const GenRec& gen, HistRec& hist, CtrlState& ctrl) {
    stor_io::read_hist(path, gen, hist);
    stor_io::read_ctrl(path, gen, ctrl);
    return 0;
}

}  // namespace stor_layout
