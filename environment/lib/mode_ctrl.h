#ifndef MODE_CTRL_H
#define MODE_CTRL_H

int mode_start_state(const char *state_dir);
int mode_seal_state(const char *state_dir, const char *trace_digest);

#endif
