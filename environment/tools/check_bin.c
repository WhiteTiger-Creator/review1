#include "ship_api.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static char *read_text(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        return NULL;
    }
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return NULL;
    }
    long sz = ftell(f);
    if (sz < 0) {
        fclose(f);
        return NULL;
    }
    if (fseek(f, 0, SEEK_SET) != 0) {
        fclose(f);
        return NULL;
    }
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    size_t n = fread(buf, 1, (size_t)sz, f);
    fclose(f);
    buf[n] = '\0';
    return buf;
}

static void extract_field(const char *body, const char *key, char *out, size_t out_len) {
    out[0] = '\0';
    char pat[96];
    snprintf(pat, sizeof(pat), "\"%s\":\"", key);
    const char *p = strstr(body, pat);
    if (!p) {
        return;
    }
    p += strlen(pat);
    size_t i = 0;
    while (*p && *p != '"' && i + 1 < out_len) {
        out[i++] = *p++;
    }
    out[i] = '\0';
}

int main(int argc, char **argv) {
    const char *out = "/app/output";
    const char *pack = "";
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--out") == 0 && i + 1 < argc) {
            out = argv[++i];
        } else if (strcmp(argv[i], "--pack") == 0 && i + 1 < argc) {
            pack = argv[++i];
        }
    }
    if (!pack[0]) {
        pack = pack_label_from_env();
    }

    char digpath[SHIP_MAX_PATH];
    snprintf(digpath, sizeof(digpath), "%s/canonical_export.sha256", out);
    char *digest = read_text(digpath);
    if (!digest) {
        fprintf(stderr, "missing digest\n");
        return 2;
    }
    char *nl = strchr(digest, '\n');
    if (nl) {
        *nl = '\0';
    }

    char tpath[SHIP_MAX_PATH];
    snprintf(tpath, sizeof(tpath), "%s/reconcile_trace.jsonl", out);
    char *trace = read_text(tpath);
    if (!trace) {
        free(digest);
        fprintf(stderr, "missing trace\n");
        return 2;
    }
    char selected[SHIP_MAX_ID];
    char note[SHIP_MAX_NOTE];
    extract_field(trace, "selected_id", selected, sizeof(selected));
    extract_field(trace, "note_text", note, sizeof(note));

    char archive[SHIP_MAX_PATH];
    snprintf(archive, sizeof(archive), "%s/counterexample_archive", out);
    char rmcmd[SHIP_MAX_PATH + 32];
    snprintf(rmcmd, sizeof(rmcmd), "rm -rf %s", archive);
    system(rmcmd);
    mkdir(archive, 0755);

    char prefix[SHIP_PREFIX + 1];
    snprintf(prefix, sizeof(prefix), "%.12s", digest);
    char case_id[96];
    snprintf(case_id, sizeof(case_id), "case_%s", pack);
    if (memo_pack(case_id, selected, note, prefix, pack, archive) != 0) {
        free(digest);
        free(trace);
        return 2;
    }
    memo_scan(archive);
    free(digest);
    free(trace);
    return 0;
}
