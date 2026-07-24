#include "segment.h"

#include "common.h"
#include "profile.h"
#include "stage_bind.h"
#include "stage_emit.h"
#include "stage_jac.h"
#include "stage_step.h"

#include <math.h>

static double tile_lambda_val(int tile, const struct model_spec *spec, double shift_add) {
    double lam = spec->diag[tile] + spec->shift + shift_add;
    if (tile > 0) {
        lam -= fabs(spec->off[tile - 1]);
    }
    if (tile + 1 < spec->n) {
        lam -= fabs(spec->off[tile]);
    }
    return lam;
}

double segment_effective_shift(double bind_seed, int generation) {
    if (generation <= 0 || bind_seed <= 0.0) {
        return 0.0;
    }
    return Q7_BIND_K * bind_seed;
}

double segment_tile_reported(
    const struct model_spec *spec,
    int tile,
    int profile_id,
    double dt,
    double bind_seed,
    int generation,
    char *emit_lane,
    size_t emit_lane_sz
) {
    double shift_add = segment_effective_shift(bind_seed, generation);
    double lam = tile_lambda_val(tile, spec, shift_add);

    struct ast_node node;
    node.kind = AST_MUL;
    node.leaf = lam;
    node.left = NULL;
    node.right = NULL;

    double lam_emit = stage_emit_lambda(&node, tile + 1, profile_id);
    stage_emit_lane(emit_lane, emit_lane_sz, lam_emit, tile + 1);

    double chain_part = stage_bind_chain(fabs(lam) * dt * 0.1, profile_id);

    double denom = 1.0 - dt * lam_emit;
    if (fabs(denom) < 1.0e-14) {
        return 0.0;
    }

    double tiles[Q7_MAX_TILES];
    for (int j = 0; j < spec->n; j++) {
        double lj = tile_lambda_val(j, spec, shift_add);
        struct ast_node nj;
        nj.kind = AST_MUL;
        nj.leaf = lj;
        double ej = stage_emit_lambda(&nj, j + 1, profile_id);
        double dj = 1.0 - dt * ej;
        tiles[j] = (fabs(dj) < 1.0e-14) ? 0.0 : (1.0 / dj);
    }

    double assembled[Q7_MAX_TILES];
    struct jac_cfg cfg = {
        .profile_id = profile_id,
        .shift = spec->shift + shift_add,
        .dt = dt,
        .bind_seed = bind_seed,
        .generation = generation,
    };
    stage_jac_assemble(tiles, (size_t)spec->n, assembled, &cfg);

    double J = assembled[tile];
    double pipeline = assembled[tile] * (1.0 + chain_part * profile_scale(profile_id));
    double u = pipeline;
    double rhs = u * 0.01;
    struct step_ctx ctx = {
        .profile_id = profile_id,
        .dt = dt,
        .stab_cap = Q7_STAB_CAP,
        .bind_seed = bind_seed,
        .generation = generation,
    };
    (void)stage_step_advance(&J, &rhs, dt, &u, &ctx);
    if (dt >= Q7_LARGE_DT) {
        return u;
    }
    return pipeline;
}
