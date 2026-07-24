#include "validate.hpp"

#include "io.hpp"
#include "layout.hpp"

#include "../core/advance.hpp"

#include <cmath>
#include <vector>

namespace {

bool datasets_present(const GenRec& gen) {
    for (int r = 0; r < gen.nproc_write; ++r) {
        std::vector<double> owned, glo, ghi;
        std::vector<int> gids;
        try {
            if (stor_layout::load_rank(gen.store_path, gen, r, owned, glo, ghi, gids) != 0) {
                return false;
            }
        } catch (...) {
            return false;
        }
        if (owned.empty() || gids.size() != owned.size()) {
            return false;
        }
    }
    return true;
}

}  // namespace

bool stor_validate_generation(const Bag& bag, const GenRec& gen) {
    (void)bag;
    if (gen.marker != 1) {
        return false;
    }
    if (gen.layout_ver < 1 || gen.layout_ver > 3) {
        return false;
    }
    return datasets_present(gen);
}
