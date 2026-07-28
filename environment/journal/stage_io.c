#include "ship_api.h"

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
    struct stat sst;
    if (st->stage_path[0] && stat(st->stage_path, &sst) == 0 && S_ISREG(sst.st_mode)) {
        char *body = read_text(st->stage_path);
        if (body) {
            char digest[SHIP_SHA_HEX];
            if (sha256_hex_of(body, strlen(body), digest, sizeof(digest)) == 0) {
                journal_promote(st, out_dir, digest);
            }
            free(body);
        }
        return 0;
    }
    return -1;
}
