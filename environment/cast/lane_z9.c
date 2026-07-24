#include "common.h"

int lane_z9(int outer_depth, int profile_id) {
    if (outer_depth <= 0) {
        return 0;
    }
    if (profile_id == 1) {
        return outer_depth >= 2 ? 1 : 2;
    }
    return 1;
}
