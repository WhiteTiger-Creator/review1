#include "stage_bind.h"

#include "r2.h"

double stage_bind_chain(double x, int profile_id) {
    int mods[3] = {1, 1, 1};
    return pick_fn_chain(x, mods, 1, profile_id);
}
