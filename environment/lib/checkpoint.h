#ifndef CHECKPOINT_H
#define CHECKPOINT_H

#include <stddef.h>

#define Q7_STATE_SLOTS 2
#define Q7_DIGEST_LEN 17
#define Q7_BIND_SCALE 1.0e-10
#define Q7_LINEAGE_K 0.25

struct q7_slot {
    int sealed;
    char digest[Q7_DIGEST_LEN];
    double bind_seed;
    double lineage_seed;
    int slot_generation;
};

struct q7_checkpoint {
    int generation;
    int active_slot;
    int segment_id;
    struct q7_slot slots[Q7_STATE_SLOTS];
};

double checkpoint_bind_seed_decode(const char *digest_hex);
int checkpoint_start(const char *state_dir);
int checkpoint_load(const char *state_dir, struct q7_checkpoint *out);
int checkpoint_save(const char *state_dir, const struct q7_checkpoint *cp);
int checkpoint_resume_bind_seed(const char *state_dir, double *bind_seed, int *generation);
int checkpoint_seal(const char *state_dir, const char *trace_digest);
int checkpoint_after_run(const char *state_dir, const char *trace_digest, int profile_id);

#endif
