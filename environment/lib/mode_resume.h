#ifndef MODE_RESUME_H
#define MODE_RESUME_H

int mode_resume_state(const char *state_dir, double *bind_seed, int *generation);
int mode_record_run(const char *state_dir, const char *trace_digest, int profile_id);

#endif
