#include "checkpoint.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char g_state_path[512];

static void slot_path(char *out, size_t outsz, const char *state_dir, int slot) {
    snprintf(out, outsz, "%s/slot_%d.json", state_dir, slot);
}

double checkpoint_bind_seed_decode(const char *digest_hex) {
    if (!digest_hex || strlen(digest_hex) < 8) {
        return 0.0;
    }
    char buf[9];
    memcpy(buf, digest_hex, 8);
    buf[8] = '\0';
    unsigned long v = strtoul(buf, NULL, 16);
    return (double)v * Q7_BIND_SCALE;
}

static int write_slot(const char *path, const struct q7_slot *slot) {
    FILE *fp = fopen(path, "w");
    if (!fp) {
        return -1;
    }
    fprintf(
        fp,
        "{\"sealed\":%d,\"digest\":\"%s\",\"bind_seed\":%.17g}\n",
        slot->sealed,
        slot->digest,
        slot->bind_seed
    );
    fclose(fp);
    return 0;
}

static int read_slot(const char *path, struct q7_slot *slot) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        return -1;
    }
    char buf[256];
    size_t n = fread(buf, 1, sizeof(buf) - 1, fp);
    fclose(fp);
    if (n < 24) {
        return -1;
    }
    buf[n] = '\0';
    memset(slot, 0, sizeof(*slot));
    const char *sealed = strstr(buf, "\"sealed\"");
    if (sealed) {
        sealed = strchr(sealed, ':');
        if (sealed) {
            slot->sealed = atoi(sealed + 1);
        }
    }
    const char *digest = strstr(buf, "\"digest\"");
    if (digest) {
        digest = strchr(digest, ':');
        if (digest) {
            digest++;
            while (*digest == ' ' || *digest == '\t') {
                digest++;
            }
            if (*digest == '"') {
                digest++;
                snprintf(slot->digest, sizeof(slot->digest), "%.16s", digest);
                char *end = strchr(slot->digest, '"');
                if (end) {
                    *end = '\0';
                }
            }
        }
    }
    const char *seed = strstr(buf, "\"bind_seed\"");
    if (seed) {
        seed = strchr(seed, ':');
        if (seed) {
            slot->bind_seed = strtod(seed + 1, NULL);
        }
    }
    return 0;
}

int checkpoint_start(const char *state_dir) {
    struct q7_checkpoint cp;
    memset(&cp, 0, sizeof(cp));
    cp.active_slot = 0;
    cp.segment_id = 1;
    return checkpoint_save(state_dir, &cp);
}

int checkpoint_load(const char *state_dir, struct q7_checkpoint *out) {
    char head[512];
    snprintf(head, sizeof(head), "%s/head.json", state_dir);
    FILE *fp = fopen(head, "r");
    if (!fp) {
        return -1;
    }
    char buf[256];
    size_t n = fread(buf, 1, sizeof(buf) - 1, fp);
    fclose(fp);
    if (n == 0) {
        return -1;
    }
    buf[n] = '\0';
    memset(out, 0, sizeof(*out));
    const char *gen = strstr(buf, "\"generation\"");
    if (gen) {
        gen = strchr(gen, ':');
        if (gen) {
            out->generation = atoi(gen + 1);
        }
    }
    const char *slot = strstr(buf, "\"active_slot\"");
    if (slot) {
        slot = strchr(slot, ':');
        if (slot) {
            out->active_slot = atoi(slot + 1);
        }
    }
    const char *seg = strstr(buf, "\"segment_id\"");
    if (seg) {
        seg = strchr(seg, ':');
        if (seg) {
            out->segment_id = atoi(seg + 1);
        }
    }
    char path[512];
    for (int i = 0; i < Q7_STATE_SLOTS; i++) {
        slot_path(path, sizeof(path), state_dir, i);
        if (read_slot(path, &out->slots[i]) != 0) {
            memset(&out->slots[i], 0, sizeof(out->slots[i]));
        }
    }
    return 0;
}

int checkpoint_save(const char *state_dir, const struct q7_checkpoint *cp) {
    char head[512];
    snprintf(head, sizeof(head), "%s/head.json", state_dir);
    FILE *fp = fopen(head, "w");
    if (!fp) {
        return -1;
    }
    fprintf(
        fp,
        "{\"generation\":%d,\"active_slot\":%d,\"segment_id\":%d}\n",
        cp->generation,
        cp->active_slot,
        cp->segment_id
    );
    fclose(fp);
    char path[512];
    for (int i = 0; i < Q7_STATE_SLOTS; i++) {
        slot_path(path, sizeof(path), state_dir, i);
        if (write_slot(path, &cp->slots[i]) != 0) {
            return -1;
        }
    }
    snprintf(g_state_path, sizeof(g_state_path), "%s", state_dir);
    return 0;
}

int checkpoint_after_run(const char *state_dir, const char *trace_digest, int profile_id) {
    (void)profile_id;
    struct q7_checkpoint cp;
    if (checkpoint_load(state_dir, &cp) != 0) {
        return -1;
    }
    int slot = cp.active_slot;
    snprintf(cp.slots[slot].digest, sizeof(cp.slots[slot].digest), "%s", trace_digest);
    cp.slots[slot].sealed = 0;
    cp.slots[slot].bind_seed = 0.0;
    return checkpoint_save(state_dir, &cp);
}

int checkpoint_seal(const char *state_dir, const char *trace_digest) {
    struct q7_checkpoint cp;
    if (checkpoint_load(state_dir, &cp) != 0) {
        return -1;
    }
    int slot = cp.active_slot;
    snprintf(cp.slots[slot].digest, sizeof(cp.slots[slot].digest), "%s", trace_digest);
    cp.slots[slot].sealed = 1;
    cp.slots[slot].bind_seed = checkpoint_bind_seed_decode(trace_digest);
    cp.generation += 1;
    cp.active_slot = (cp.active_slot + 1) % Q7_STATE_SLOTS;
    return checkpoint_save(state_dir, &cp);
}

int checkpoint_resume_bind_seed(const char *state_dir, double *bind_seed, int *generation) {
    struct q7_checkpoint cp;
    if (checkpoint_load(state_dir, &cp) != 0) {
        return -1;
    }
    int found = 0;
    for (int i = 0; i < Q7_STATE_SLOTS; i++) {
        if (cp.slots[i].sealed && cp.slots[i].digest[0]) {
            found = 1;
            break;
        }
    }
    if (!found) {
        return 64;
    }
    (void)state_dir;
    if (bind_seed) {
        *bind_seed = 0.0;
    }
    if (generation) {
        *generation = cp.generation;
    }
    cp.segment_id += 1;
    return checkpoint_save(state_dir, &cp);
}
