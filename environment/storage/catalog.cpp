#include "catalog.hpp"

#include "io.hpp"
#include "layout.hpp"
#include "validate.hpp"

#include <algorithm>
#include <stdexcept>
#include <vector>

GenRec stor_catalog_select(const Bag& bag) {
    std::vector<int> ids;
    stor_io::list_gen_ids(bag.store_path, ids);
    if (ids.empty()) {
        throw std::runtime_error("catalog: no generations");
    }
    std::sort(ids.begin(), ids.end(), std::greater<int>());
    for (int id : ids) {
        GenRec gen{};
        stor_layout::load_meta(bag.store_path, id, gen);
        gen.store_path = bag.store_path;
        if (gen.marker == 1) {
            return gen;
        }
    }
    throw std::runtime_error("catalog: no committed generation");
}
