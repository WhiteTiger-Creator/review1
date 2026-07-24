#ifndef Q7_COMMON_H
#define Q7_COMMON_H

#include <stddef.h>

#define Q7_MAX_TILES 8
#define Q7_MAX_N 8
#define Q7_ELEM_TOL 1.0e-10
#define Q7_COARSE_BAND 1.0e-6
#define Q7_FINE_BAND 1.0e-8
#define Q7_LARGE_DT 0.28
#define Q7_STAB_CAP 2.0
#define Q7_BUF 128
#define Q7_BIND_K 1.0e-6
#define Q7_LINEAGE_K 0.25

extern int q7_active_profile;

struct model_spec {
    char name[32];
    int n;
    double shift;
    double diag[Q7_MAX_N];
    double off[Q7_MAX_N - 1];
    double dt_fine[2];
    double dt_large;
    double dt_step;
};

struct trace_row {
    char tile_id[16];
    double reported;
    double reference;
    char profile[16];
    char emit_lane[8];
};

struct jac_cfg {
    int profile_id;
    double shift;
    double dt;
    double bind_seed;
    int generation;
};

struct step_ctx {
    int profile_id;
    double dt;
    double stab_cap;
    double bind_seed;
    int generation;
};

int profile_id_from_name(const char *name);
const char *profile_name_from_id(int profile_id);

#endif
