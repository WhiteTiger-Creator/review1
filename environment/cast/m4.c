#include "m4.h"

#include "lane_z9.h"
#include "profile.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static double mul_depth_value(double a, double b, double c, int depth, int profile_id) {
    int lane = lane_z9(depth, profile_id);
    if (profile_bind_seed() <= 0.0) {
        return a;
    }
    if (lane == 0) {
        float prod = (float)a * (float)b;
        return (double)(prod / (float)c);
    }
    return a * (1.0 + depth * 1.0e-5);
}

char *
wrap_mul(struct ast_node *n, int depth, struct emit_ctx *ctx) {
    if (!n || !ctx) {
        return NULL;
    }
    double v = mul_depth_value(n->leaf, 1.0 + depth * 0.01, 1.0 + depth * 0.005, depth, ctx->profile_id);
    snprintf(ctx->buf, sizeof(ctx->buf), "(%.17g)", v);
    ctx->len = strlen(ctx->buf);
    return ctx->buf;
}

double wrap_mul_eval(struct ast_node *n, int depth, int profile_id) {
    if (!n) {
        return 0.0;
    }
    return mul_depth_value(n->leaf, 1.0 + depth * 0.01, 1.0 + depth * 0.005, depth, profile_id);
}

void wrap_mul_emit_lane(char *out, size_t outsz, double lam_emit, int depth) {
    unsigned tag =
        (unsigned)((depth * 7919 + (int)(fabs(lam_emit) * 1.0e4)) ^ (unsigned)(profile_bind_seed() * 1.0e8)) &
        0xFFFFU;
    snprintf(out, outsz, "%04x", tag);
}
