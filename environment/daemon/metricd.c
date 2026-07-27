#include "ship_api.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int write_text(const char *path, const char *body) {
    FILE *f = fopen(path, "wb");
    if (!f) {
        return -1;
    }
    fputs(body, f);
    fclose(f);
    return 0;
}

static int append_text(const char *path, const char *body) {
    FILE *f = fopen(path, "ab");
    if (!f) {
        return -1;
    }
    fputs(body, f);
    fclose(f);
    return 0;
}

static void usage(void) {
    fprintf(stderr, "usage: metricd --book PATH --snaps PATH --out PATH\n");
}

static int emit_trace(const char *out, const char *selected_id, const char *note,
                      const char *prefix, const char *pack, int append_mode) {
    char trace[512];
    snprintf(trace, sizeof(trace),
             "{\"event\":\"ship_complete\",\"selected_id\":\"%s\",\"note_text\":\"%s\","
             "\"sha_prefix\":\"%s\",\"pack_label\":\"%s\"}\n",
             selected_id, note, prefix, pack);
    char tpath[SHIP_MAX_PATH];
    snprintf(tpath, sizeof(tpath), "%s/reconcile_trace.jsonl", out);
    if (append_mode) {
        return append_text(tpath, trace);
    }
    return write_text(tpath, trace);
}

int main(int argc, char **argv) {
    const char *book = "/app/fixtures/exclbook/base.json";
    const char *snaps = "/app/fixtures/snaps";
    const char *out = "/app/output";
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--book") == 0 && i + 1 < argc) {
            book = argv[++i];
        } else if (strcmp(argv[i], "--snaps") == 0 && i + 1 < argc) {
            snaps = argv[++i];
        } else if (strcmp(argv[i], "--out") == 0 && i + 1 < argc) {
            out = argv[++i];
        } else {
            usage();
            return 2;
        }
    }

    const char *pack = pack_label_from_env();

    LedgerView view;
    if (book_load(book, &view) != 0) {
        fprintf(stderr, "book load failed\n");
        return 2;
    }
    char stamp[SHIP_SHA_HEX];
    if (book_stamp(book, stamp, sizeof(stamp)) != 0) {
        fprintf(stderr, "book stamp failed\n");
        return 2;
    }

    JournalState prior;
    int have_prior = journal_load(out, &prior) == 0;

    if (have_prior && prior.complete && strcmp(prior.book_stamp, stamp) == 0) {
        char digpath[SHIP_MAX_PATH];
        snprintf(digpath, sizeof(digpath), "%s/canonical_export.sha256", out);
        char digest[SHIP_SHA_HEX];
        digest[0] = '\0';
        FILE *df = fopen(digpath, "rb");
        if (df) {
            if (fgets(digest, sizeof(digest), df)) {
                char *nl = strchr(digest, '\n');
                if (nl) {
                    *nl = '\0';
                }
            }
            fclose(df);
        }
        char prefix[SHIP_PREFIX + 1];
        snprintf(prefix, sizeof(prefix), "%.12s", digest);
        char note[SHIP_MAX_NOTE];
        snprintf(note, sizeof(note), "picked=%s;reused=1", prior.selected_id);
        emit_trace(out, prior.selected_id, note, prefix, prior.pack_label[0] ? prior.pack_label : pack,
                   0);
        return 0;
    }

    if (have_prior && !prior.complete) {
        if (journal_recover(out, &prior) == 0 && prior.complete) {
            char digpath[SHIP_MAX_PATH];
            snprintf(digpath, sizeof(digpath), "%s/canonical_export.sha256", out);
            char digest[SHIP_SHA_HEX];
            digest[0] = '\0';
            FILE *df = fopen(digpath, "rb");
            if (df) {
                if (fgets(digest, sizeof(digest), df)) {
                    char *nl = strchr(digest, '\n');
                    if (nl) {
                        *nl = '\0';
                    }
                }
                fclose(df);
            }
            char prefix[SHIP_PREFIX + 1];
            snprintf(prefix, sizeof(prefix), "%.12s", digest);
            char note[SHIP_MAX_NOTE];
            snprintf(note, sizeof(note), "picked=%s;recovered=1", prior.selected_id);
            emit_trace(out, prior.selected_id, note, prefix, pack, 0);
            return 0;
        }
    }

    SnapRef cands[SHIP_MAX_CANDS];
    int n = 0;
    if (scan_snaps(snaps, &view, cands, &n) != 0 || n == 0) {
        fprintf(stderr, "no candidate\n");
        return 2;
    }
    char listing[4096];
    rank_list(cands, n, listing, sizeof(listing));
    char lpath[SHIP_MAX_PATH];
    snprintf(lpath, sizeof(lpath), "%s/cand_listing.txt", out);
    write_text(lpath, listing);

    SnapRef chosen = rank_pick(cands, n, &view);
    if (!chosen.id[0]) {
        fprintf(stderr, "no pick\n");
        return 2;
    }

    int generation = 1;
    if (have_prior) {
        generation = prior.generation + 1;
    }
    JournalState st;
    if (journal_begin(out, chosen.id, stamp, pack, generation, &st) != 0) {
        fprintf(stderr, "journal begin failed\n");
        return 2;
    }

    MetricRow rows[SHIP_MAX_ROWS];
    int n_rows = 0;
    if (load_metrics(chosen.path, rows, &n_rows) != 0 || n_rows == 0) {
        fprintf(stderr, "metrics load failed\n");
        return 2;
    }
    char legacy[SHIP_MAX_LINE];
    for (int i = 0; i < n_rows; i++) {
        fmt_lane_legacy(rows[i].key, rows[i].val, legacy, sizeof(legacy));
    }

    char body[8192];
    if (stage_emit(rows, n_rows, body, sizeof(body)) != 0) {
        fprintf(stderr, "emit failed\n");
        return 2;
    }
    if (journal_write_stage(&st, body) != 0) {
        fprintf(stderr, "stage write failed\n");
        return 2;
    }

    char digest[SHIP_SHA_HEX];
    if (sha256_hex_of(body, strlen(body), digest, sizeof(digest)) != 0) {
        fprintf(stderr, "hash failed\n");
        return 2;
    }
    if (journal_promote(&st, out, digest) != 0) {
        fprintf(stderr, "promote failed\n");
        return 2;
    }

    char note[SHIP_MAX_NOTE];
    snprintf(note, sizeof(note), "picked=%s;tier=%d", chosen.id, chosen.tier);
    char prefix[SHIP_PREFIX + 1];
    snprintf(prefix, sizeof(prefix), "%.12s", digest);
    emit_trace(out, chosen.id, note, prefix, pack, 0);
    return 0;
}
