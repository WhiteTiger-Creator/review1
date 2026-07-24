#include "ledger.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int digest_body(char *out16, const char *body_path) {
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "sha256sum %s", body_path);
    FILE *fp = popen(cmd, "r");
    if (!fp) {
        return -1;
    }
    char hex[128];
    if (!fgets(hex, sizeof(hex), fp)) {
        pclose(fp);
        return -1;
    }
    pclose(fp);
    for (int i = 0; i < 16; i++) {
        out16[i] = hex[i];
    }
    out16[16] = '\0';
    return 0;
}

static void write_row(FILE *body, const struct trace_row *row, int first) {
    if (!first) {
        fprintf(body, ",");
    }
    fprintf(
        body,
        "{\"tile_id\":\"%s\",\"reported\":%.17g,\"reference\":%.17g,\"profile\":\"%s\",\"emit_lane\":\"%s\"}",
        row->tile_id,
        row->reported,
        row->reference,
        row->profile,
        row->emit_lane
    );
}

int ledger_write_json(const char *path, struct trace_row *rows, int count) {
    char body_path[] = "/tmp/q7_body.json";
    FILE *body = fopen(body_path, "w");
    if (!body) {
        return -1;
    }
    fprintf(body, "{\"rows\":[");
    for (int i = 0; i < count; i++) {
        write_row(body, &rows[i], i == 0);
    }
    fprintf(body, "]}");
    fclose(body);

    char digest[17];
    if (digest_body(digest, body_path) != 0) {
        return -1;
    }

    FILE *out = fopen(path, "w");
    if (!out) {
        return -1;
    }
    fprintf(out, "{\"rows\":[");
    for (int i = 0; i < count; i++) {
        write_row(out, &rows[i], i == 0);
    }
    fprintf(out, "],\"repro_digest\":\"%s\"}", digest);
    fclose(out);
    remove(body_path);
    return 0;
}
