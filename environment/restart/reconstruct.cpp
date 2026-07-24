#include "reconstruct.hpp"

#include "../storage/layout.hpp"

#include <stdexcept>
#include <vector>

GlobRec restart_reconstruct(const GenRec& gen, const Bag& bag) {
    GlobRec out{};
    out.ncell = bag.n_global;
    out.step = gen.step;
    out.vals.assign(static_cast<size_t>(bag.n_global), 0.0);
    out.gids.clear();

    int cursor = 0;
    for (int r = 0; r < gen.nproc_write; ++r) {
        std::vector<double> owned, glo, ghi;
        std::vector<int> gids;
        stor_layout::load_rank(gen.store_path, gen, r, owned, glo, ghi, gids);
        for (double v : owned) {
            if (cursor < bag.n_global) {
                out.vals[static_cast<size_t>(cursor++)] = v;
            }
        }
        for (double v : glo) {
            if (cursor < bag.n_global) {
                out.vals[static_cast<size_t>(cursor++)] = v;
            }
        }
        for (double v : ghi) {
            if (cursor < bag.n_global) {
                out.vals[static_cast<size_t>(cursor++)] = v;
            }
        }
    }
    for (int i = 0; i < bag.n_global; ++i) {
        out.gids.push_back(i);
    }

    HistRec hist{};
    CtrlState ctrl{};
    stor_layout::load_hist_ctrl(gen.store_path, gen, hist, ctrl);
    out.dt_seq = hist.dt_seq;
    out.m_seq = hist.m_seq;
    out.ctrl = ctrl;
    return out;
}
