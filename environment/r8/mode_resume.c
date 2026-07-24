#include "mode_resume.h"

#include "checkpoint.h"

int mode_resume_state(const char *state_dir, double *bind_seed, int *generation) {
    return checkpoint_resume_bind_seed(state_dir, bind_seed, generation);
}

int mode_record_run(const char *state_dir, const char *trace_digest, int profile_id) {
    return checkpoint_after_run(state_dir, trace_digest, profile_id);
}
