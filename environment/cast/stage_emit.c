#include "stage_emit.h"

#include "m4.h"

double stage_emit_lambda(struct ast_node *node, int depth, int profile_id) {
    return wrap_mul_eval(node, depth, profile_id);
}

void stage_emit_lane(char *out, size_t outsz, double lam_emit, int depth) {
    wrap_mul_emit_lane(out, outsz, lam_emit, depth);
}
