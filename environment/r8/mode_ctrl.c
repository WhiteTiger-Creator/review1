#include "mode_ctrl.h"

#include "checkpoint.h"

int mode_start_state(const char *state_dir) {
    return checkpoint_start(state_dir);
}

int mode_seal_state(const char *state_dir, const char *trace_digest) {
    return checkpoint_seal(state_dir, trace_digest);
}
