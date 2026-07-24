#include "common.h"
#include "fixt_load.h"
#include "profile.h"
#include "ledger.h"
#include "mode_ctrl.h"
#include "mode_resume.h"
#include "segment.h"
#include "z9_val.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int ensure_dir(const char *path) {
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "mkdir -p %s", path);
    return system(cmd);
}

static int read_trace_digest(const char *trace_out, char *digest, size_t digest_sz) {
    FILE *fp = fopen(trace_out, "r");
    if (!fp) {
        return -1;
    }
    char buf[4096];
    size_t n = fread(buf, 1, sizeof(buf) - 1, fp);
    fclose(fp);
    if (n == 0) {
        return -1;
    }
    buf[n] = '\0';
    const char *dig = strstr(buf, "\"repro_digest\"");
    if (!dig) {
        return -1;
    }
    dig = strchr(dig, ':');
    if (!dig) {
        return -1;
    }
    dig++;
    while (*dig == ' ') {
        dig++;
    }
    if (*dig != '"') {
        return -1;
    }
    dig++;
    snprintf(digest, digest_sz, "%.16s", dig);
    char *end = strchr(digest, '"');
    if (end) {
        *end = '\0';
    }
    return 0;
}

static int run_segment(
    const char *model_path,
    const char *trace_out,
    const char *profile_name,
    double dt_override,
    double bind_seed,
    int generation
) {
    struct model_spec spec;
    if (fixt_load_json(model_path, &spec) != 0) {
        return 1;
    }
    int profile_id = profile_id_from_name(profile_name);
    profile_set_active(profile_id);
    profile_set_runtime(bind_seed, generation);

    struct trace_row rows[Q7_MAX_TILES];
    int row_count = 0;
    double dt = dt_override >= 0.0 ? dt_override : spec.dt_step;
    double shift_add = segment_effective_shift(bind_seed, generation);

    for (int tile = 0; tile < spec.n; tile++) {
        struct trace_row *row = &rows[row_count++];
        snprintf(row->tile_id, sizeof(row->tile_id), "%d", tile);
        row->reference = v9_elem_shift(tile, &spec, dt, profile_id, shift_add);
        row->reported = segment_tile_reported(
            &spec, tile, profile_id, dt, bind_seed, generation, row->emit_lane, sizeof(row->emit_lane)
        );
        snprintf(row->profile, sizeof(row->profile), "%s", profile_name);
    }

    if (ledger_write_json(trace_out, rows, row_count) != 0) {
        return 1;
    }
    return 0;
}

int run_driver_mode(
    const char *mode,
    const char *state_dir,
    const char *model_path,
    const char *trace_out,
    const char *profile_name,
    double dt_override
) {
    if (!mode || !state_dir || !trace_out) {
        return 2;
    }
    if (strcmp(mode, "seal") == 0) {
        char digest[17];
        if (read_trace_digest(trace_out, digest, sizeof(digest)) != 0) {
            return 1;
        }
        return mode_seal_state(state_dir, digest);
    }

    if (!model_path) {
        return 2;
    }

    ensure_dir(state_dir);
    double bind_seed = 0.0;
    int generation = 0;

    if (strcmp(mode, "start") == 0) {
        if (mode_start_state(state_dir) != 0) {
            return 1;
        }
    } else if (strcmp(mode, "resume") == 0) {
        int rc = mode_resume_state(state_dir, &bind_seed, &generation);
        if (rc != 0) {
            return rc;
        }
    } else {
        return 2;
    }

    int rc = run_segment(model_path, trace_out, profile_name, dt_override, bind_seed, generation);
    if (rc != 0) {
        return rc;
    }

    char digest[17];
    if (read_trace_digest(trace_out, digest, sizeof(digest)) != 0) {
        return 1;
    }
    if (mode_record_run(state_dir, digest, profile_id_from_name(profile_name)) != 0) {
        return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    const char *mode = NULL;
    const char *state_dir = NULL;
    const char *model = NULL;
    const char *trace_out = NULL;
    const char *profile = "nominal";
    double dt_override = -1.0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--mode") == 0 && i + 1 < argc) {
            mode = argv[++i];
        } else if (strcmp(argv[i], "--state-dir") == 0 && i + 1 < argc) {
            state_dir = argv[++i];
        } else if (strcmp(argv[i], "--model") == 0 && i + 1 < argc) {
            model = argv[++i];
        } else if (strcmp(argv[i], "--trace-out") == 0 && i + 1 < argc) {
            trace_out = argv[++i];
        } else if (strcmp(argv[i], "--profile") == 0 && i + 1 < argc) {
            profile = argv[++i];
        } else if (strcmp(argv[i], "--dt") == 0 && i + 1 < argc) {
            dt_override = atof(argv[++i]);
        }
    }
    if (!mode || !state_dir || !trace_out) {
        fprintf(
            stderr,
            "usage: q7 --mode {start|resume|seal} --state-dir PATH --trace-out PATH "
            "[--model PATH] [--profile nominal|scaled] [--dt SECONDS]\n"
        );
        return 2;
    }
    return run_driver_mode(mode, state_dir, model, trace_out, profile, dt_override);
}
