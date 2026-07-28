#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from pathlib import Path

root = Path("/app/environment")

(root / "emit" / "fmt_lane.c").write_text(
    r'''#include "ship_api.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void fmt_lane(const char *key, double val, int scale, char *out, size_t out_len) {
    char num[96];
    snprintf(num, sizeof(num), "%.*f", scale, val);
    snprintf(out, out_len, "%s=%s", key, num);
}

void fmt_lane_legacy(const char *key, double val, char *out, size_t out_len) {
    snprintf(out, out_len, "%s~%.3f", key, val);
}
'''
)

(root / "pick" / "rank_pick.c").write_text(
    r'''#include "ship_api.h"

#include <stdio.h>
#include <string.h>

static int tier_of(const SnapRef *ref, const LedgerView *view) {
    for (int i = 0; i < view->n_entries; i++) {
        if (strcmp(view->entries[i].id, ref->id) == 0) {
            return view->entries[i].tier;
        }
    }
    return ref->tier;
}

static int reaches(const char *src, const char *dst, const LedgerView *view) {
    char seen[SHIP_MAX_CANDS][SHIP_MAX_ID];
    int n_seen = 0;
    char stack[SHIP_MAX_CANDS][SHIP_MAX_ID];
    int n_stack = 0;
    snprintf(stack[n_stack++], SHIP_MAX_ID, "%s", src);
    while (n_stack > 0) {
        char cur[SHIP_MAX_ID];
        snprintf(cur, sizeof(cur), "%s", stack[--n_stack]);
        int already = 0;
        for (int i = 0; i < n_seen; i++) {
            if (strcmp(seen[i], cur) == 0) {
                already = 1;
                break;
            }
        }
        if (already) {
            continue;
        }
        snprintf(seen[n_seen++], SHIP_MAX_ID, "%s", cur);
        for (int i = 0; i < view->n_entries; i++) {
            if (strcmp(view->entries[i].id, cur) != 0) {
                continue;
            }
            for (int j = 0; j < view->entries[i].n_super; j++) {
                if (strcmp(view->entries[i].supersedes[j], dst) == 0) {
                    return 1;
                }
                if (n_stack < SHIP_MAX_CANDS) {
                    snprintf(stack[n_stack++], SHIP_MAX_ID, "%s", view->entries[i].supersedes[j]);
                }
            }
        }
    }
    return 0;
}

SnapRef rank_pick(const SnapRef *cands, int n, const LedgerView *view) {
    SnapRef empty;
    memset(&empty, 0, sizeof(empty));
    if (n <= 0) {
        return empty;
    }
    int best_tier = tier_of(&cands[0], view);
    for (int i = 1; i < n; i++) {
        int t = tier_of(&cands[i], view);
        if (t > best_tier) {
            best_tier = t;
        }
    }
    SnapRef top[SHIP_MAX_CANDS];
    int n_top = 0;
    for (int i = 0; i < n; i++) {
        if (tier_of(&cands[i], view) == best_tier) {
            top[n_top++] = cands[i];
        }
    }
    if (n_top == 1) {
        return top[0];
    }
    SnapRef roots[SHIP_MAX_CANDS];
    int n_roots = 0;
    for (int i = 0; i < n_top; i++) {
        int dominated = 0;
        for (int j = 0; j < n_top; j++) {
            if (i == j) {
                continue;
            }
            if (reaches(top[j].id, top[i].id, view)) {
                dominated = 1;
                break;
            }
        }
        if (!dominated) {
            roots[n_roots++] = top[i];
        }
    }
    SnapRef *pool = n_roots > 0 ? roots : top;
    int n_pool = n_roots > 0 ? n_roots : n_top;
    SnapRef best = pool[0];
    for (int i = 1; i < n_pool; i++) {
        if (strcmp(pool[i].id, best.id) < 0) {
            best = pool[i];
        }
    }
    return best;
}
'''
)

(root / "journal" / "stage_io.c").write_text(
    r'''#include "ship_api.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int write_text(const char *path, const char *body) {
    FILE *f = fopen(path, "wb");
    if (!f) {
        return -1;
    }
    size_t n = strlen(body);
    if (fwrite(body, 1, n, f) != n) {
        fclose(f);
        return -1;
    }
    fclose(f);
    return 0;
}

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

int sha256_hex_of(const char *data, size_t len, char *out_hex, size_t out_len) {
    char tmp_path[] = "/tmp/ship_hash_XXXXXX";
    int fd = mkstemp(tmp_path);
    if (fd < 0) {
        return -1;
    }
    if (write(fd, data, len) != (ssize_t)len) {
        close(fd);
        unlink(tmp_path);
        return -1;
    }
    close(fd);
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "sha256sum %s", tmp_path);
    FILE *p = popen(cmd, "r");
    if (!p) {
        unlink(tmp_path);
        return -1;
    }
    if (!fgets(out_hex, (int)out_len, p)) {
        pclose(p);
        unlink(tmp_path);
        return -1;
    }
    pclose(p);
    unlink(tmp_path);
    char *sp = strchr(out_hex, ' ');
    if (sp) {
        *sp = '\0';
    }
    char *nl = strchr(out_hex, '\n');
    if (nl) {
        *nl = '\0';
    }
    return 0;
}

int journal_load(const char *out_dir, JournalState *st) {
    memset(st, 0, sizeof(*st));
    char path[SHIP_MAX_PATH];
    snprintf(path, sizeof(path), "%s/ship_journal.json", out_dir);
    char *raw = read_text(path);
    if (!raw) {
        return -1;
    }
    const char *p;
    if ((p = strstr(raw, "\"selected_id\""))) {
        const char *c = strchr(p, ':');
        if (c) {
            c = strchr(c, '"');
            if (c) {
                c++;
                size_t i = 0;
                while (*c && *c != '"' && i + 1 < sizeof(st->selected_id)) {
                    st->selected_id[i++] = *c++;
                }
                st->selected_id[i] = '\0';
            }
        }
    }
    if ((p = strstr(raw, "\"book_stamp\""))) {
        const char *c = strchr(p, ':');
        if (c) {
            c = strchr(c, '"');
            if (c) {
                c++;
                size_t i = 0;
                while (*c && *c != '"' && i + 1 < sizeof(st->book_stamp)) {
                    st->book_stamp[i++] = *c++;
                }
                st->book_stamp[i] = '\0';
            }
        }
    }
    if ((p = strstr(raw, "\"pack_label\""))) {
        const char *c = strchr(p, ':');
        if (c) {
            c = strchr(c, '"');
            if (c) {
                c++;
                size_t i = 0;
                while (*c && *c != '"' && i + 1 < sizeof(st->pack_label)) {
                    st->pack_label[i++] = *c++;
                }
                st->pack_label[i] = '\0';
            }
        }
    }
    if ((p = strstr(raw, "\"stage_path\""))) {
        const char *c = strchr(p, ':');
        if (c) {
            c = strchr(c, '"');
            if (c) {
                c++;
                size_t i = 0;
                while (*c && *c != '"' && i + 1 < sizeof(st->stage_path)) {
                    st->stage_path[i++] = *c++;
                }
                st->stage_path[i] = '\0';
            }
        }
    }
    if ((p = strstr(raw, "\"complete\""))) {
        const char *c = strchr(p, ':');
        if (c) {
            st->complete = atoi(c + 1) ? 1 : 0;
        }
    }
    if ((p = strstr(raw, "\"generation\""))) {
        const char *c = strchr(p, ':');
        if (c) {
            st->generation = atoi(c + 1);
        }
    }
    free(raw);
    return 0;
}

static int journal_save(const char *out_dir, const JournalState *st) {
    char path[SHIP_MAX_PATH];
    snprintf(path, sizeof(path), "%s/ship_journal.json", out_dir);
    char body[1280];
    snprintf(body, sizeof(body),
             "{\n  \"selected_id\": \"%s\",\n  \"book_stamp\": \"%s\",\n  \"pack_label\": "
             "\"%s\",\n  \"stage_path\": \"%s\",\n  \"complete\": %d,\n  \"generation\": %d\n}\n",
             st->selected_id, st->book_stamp, st->pack_label, st->stage_path, st->complete,
             st->generation);
    return write_text(path, body);
}

int journal_begin(const char *out_dir, const char *selected_id, const char *book_hex,
                  const char *pack_label, int generation, JournalState *st) {
    memset(st, 0, sizeof(*st));
    snprintf(st->selected_id, sizeof(st->selected_id), "%s", selected_id);
    snprintf(st->book_stamp, sizeof(st->book_stamp), "%s", book_hex);
    snprintf(st->pack_label, sizeof(st->pack_label), "%s", pack_label ? pack_label : "");
    snprintf(st->stage_path, sizeof(st->stage_path), "%s/stage/body.txt", out_dir);
    st->complete = 0;
    st->generation = generation;
    char stagedir[SHIP_MAX_PATH];
    snprintf(stagedir, sizeof(stagedir), "%s/stage", out_dir);
    mkdir(out_dir, 0755);
    mkdir(stagedir, 0755);
    return journal_save(out_dir, st);
}

int journal_write_stage(JournalState *st, const char *body) {
    return write_text(st->stage_path, body);
}

int journal_promote(JournalState *st, const char *out_dir, const char *digest_hex) {
    char digest_path[SHIP_MAX_PATH];
    snprintf(digest_path, sizeof(digest_path), "%s/canonical_export.sha256", out_dir);
    char line[SHIP_SHA_HEX + 2];
    snprintf(line, sizeof(line), "%s\n", digest_hex);
    if (write_text(digest_path, line) != 0) {
        return -1;
    }
    st->complete = 1;
    return journal_save(out_dir, st);
}

int journal_recover(const char *out_dir, JournalState *st) {
    if (journal_load(out_dir, st) != 0) {
        return -1;
    }
    if (st->complete) {
        return 0;
    }
    if (st->stage_path[0]) {
        unlink(st->stage_path);
    }
    st->complete = 0;
    st->selected_id[0] = '\0';
    journal_save(out_dir, st);
    return -1;
}
'''
)

(root / "archive" / "memo_pack.c").write_text(
    r'''#include "ship_api.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

int memo_pack(const char *case_id, const char *selected_id, const char *note_text,
              const char *sha_prefix, const char *pack_label, const char *archive_root) {
    if (!case_id || !case_id[0] || !selected_id || !selected_id[0] || !note_text ||
        !note_text[0] || !sha_prefix || !sha_prefix[0] || !pack_label || !pack_label[0]) {
        return -1;
    }
    mkdir(archive_root, 0755);
    char path[SHIP_MAX_PATH];
    snprintf(path, sizeof(path), "%s/manifest.json", archive_root);
    FILE *f = fopen(path, "wb");
    if (!f) {
        return -1;
    }
    fprintf(f,
            "{\n  \"cases\": [\n    {\n      \"case_id\": \"%s\",\n      \"selected_id\": "
            "\"%s\",\n      \"note_text\": \"%s\",\n      \"sha_prefix\": \"%s\",\n      "
            "\"pack_label\": \"%s\"\n    }\n  ]\n}\n",
            case_id, selected_id, note_text, sha_prefix, pack_label);
    fclose(f);
    return 0;
}

int memo_scan(const char *archive_root) {
    char path[SHIP_MAX_PATH];
    snprintf(path, sizeof(path), "%s/manifest.json", archive_root);
    FILE *f = fopen(path, "rb");
    if (!f) {
        return -1;
    }
    fclose(f);
    return 0;
}
'''
)

(root / "daemon" / "metricd.c").write_text(
    r'''#include "ship_api.h"

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

static int stage_ascii_ok(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        return 0;
    }
    int ch;
    while ((ch = fgetc(f)) != EOF) {
        if (ch == ',') {
            fclose(f);
            return 0;
        }
    }
    fclose(f);
    return 1;
}

static int emit_trace(const char *out, const char *selected_id, const char *note,
                      const char *prefix, const char *pack) {
    char trace[512];
    snprintf(trace, sizeof(trace),
             "{\"event\":\"ship_complete\",\"selected_id\":\"%s\",\"note_text\":\"%s\","
             "\"sha_prefix\":\"%s\",\"pack_label\":\"%s\"}\n",
             selected_id, note, prefix, pack);
    char tpath[SHIP_MAX_PATH];
    snprintf(tpath, sizeof(tpath), "%s/reconcile_trace.jsonl", out);
    return append_text(tpath, trace);
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

    if (have_prior && !prior.complete) {
        if (journal_recover(out, &prior) == 0 && prior.complete) {
            fprintf(stderr, "recover promoted incomplete stage\n");
            return 2;
        }
        have_prior = journal_load(out, &prior) == 0;
    }

    if (have_prior && prior.complete && strcmp(prior.book_stamp, stamp) == 0 &&
        strcmp(prior.pack_label, pack) == 0 && stage_ascii_ok(prior.stage_path)) {
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
        if (!digest[0]) {
            fprintf(stderr, "reuse missing digest\n");
            return 2;
        }
        char prefix[SHIP_PREFIX + 1];
        snprintf(prefix, sizeof(prefix), "%.12s", digest);
        char note[SHIP_MAX_NOTE];
        snprintf(note, sizeof(note), "picked=%s;reused=1", prior.selected_id);
        if (emit_trace(out, prior.selected_id, note, prefix, pack) != 0) {
            fprintf(stderr, "trace append failed\n");
            return 2;
        }
        return 0;
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
    if (emit_trace(out, chosen.id, note, prefix, pack) != 0) {
        fprintf(stderr, "trace append failed\n");
        return 2;
    }
    return 0;
}
'''
)
PY

chmod +x /app/environment/scripts/run_ship.sh /app/environment/scripts/seed_torn.sh
make -C /app/environment PREFIX=/app install
/app/scripts/run_ship.sh --fresh --langpack /app/fixtures/langpacks/c.langpack
/app/bin/check_bin --pack C
