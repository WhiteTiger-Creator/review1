#include "qdrift/witness_seal.h"

#include <openssl/evp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void digest_layer_order(const char *const *ids, int count, char *hex_out, int hex_len) {
    char buf[4096];
    int pos = 0;
    for (int i = 0; i < count; ++i) {
        pos += snprintf(buf + pos, sizeof(buf) - (size_t)pos, "%s", ids[i]);
    }
    unsigned char hash[32];
    EVP_MD_CTX *ctx = EVP_MD_CTX_new();
    EVP_DigestInit_ex(ctx, EVP_sha256(), NULL);
    EVP_DigestUpdate(ctx, buf, strlen(buf));
    unsigned int hash_len = 0;
    EVP_DigestFinal_ex(ctx, hash, &hash_len);
    EVP_MD_CTX_free(ctx);
    for (unsigned int i = 0; i < hash_len && (int)(i * 2 + 1) < hex_len; ++i) {
        snprintf(hex_out + i * 2, 3, "%02x", hash[i]);
    }
    hex_out[hash_len * 2] = '\0';
}

int qdrift_write_walk_witness(const char *staging_dir, const qdrift_snapshot_t *snap) {
    char idbuf[QDRIFT_MAX_LAYERS][QDRIFT_MAX_ID_LEN];
    const char *ids[QDRIFT_MAX_LAYERS];
    for (int i = 0; i < snap->layer_count; ++i) {
        strncpy(idbuf[i], snap->layers[i].layer_id, sizeof(idbuf[i]) - 1);
        ids[i] = idbuf[i];
    }
    char hex[65];
    digest_layer_order(ids, snap->layer_count, hex, sizeof(hex));
    char path[512];
    snprintf(path, sizeof(path), "%s/walk-witness.json", staging_dir);
    FILE *f = fopen(path, "w");
    if (!f) {
        return -1;
    }
    fprintf(f, "{\"layer_order_digest\":\"%s\"}\n", hex);
    fclose(f);
    return 0;
}

int qdrift_validate_walk_witness(const char *staging_dir, const qdrift_snapshot_t *snap) {
    char idbuf[QDRIFT_MAX_LAYERS][QDRIFT_MAX_ID_LEN];
    const char *ids[QDRIFT_MAX_LAYERS];
    for (int i = 0; i < snap->layer_count; ++i) {
        strncpy(idbuf[i], snap->layers[i].layer_id, sizeof(idbuf[i]) - 1);
        ids[i] = idbuf[i];
    }
    char expect[65];
    digest_layer_order(ids, snap->layer_count, expect, sizeof(expect));
    char path[512];
    snprintf(path, sizeof(path), "%s/walk-witness.json", staging_dir);
    FILE *f = fopen(path, "r");
    if (!f) {
        return -1;
    }
    char buf[256];
    fread(buf, 1, sizeof(buf) - 1, f);
    buf[sizeof(buf) - 1] = '\0';
    fclose(f);
    const char *dp = strstr(buf, "layer_order_digest");
    if (!dp) {
        return -1;
    }
    dp = strchr(dp, ':');
    if (!dp) {
        return -1;
    }
    dp = strchr(dp, '"');
    if (!dp) {
        return -1;
    }
    dp++;
    const char *de = strchr(dp, '"');
    if (!de) {
        return -1;
    }
    char got[65];
    int n = (int)(de - dp);
    if (n >= (int)sizeof(got)) {
        n = (int)sizeof(got) - 1;
    }
    memcpy(got, dp, (size_t)n);
    got[n] = '\0';
    if (strcmp(got, expect) != 0) {
        return -1;
    }
    return 0;
}

int qdrift_bump_publish_ledger(const char *graph_id, const char *witness_hex) {
    const char *ledger_dir = "/app/var/qbound-cert-ledger";
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "mkdir -p %s", ledger_dir);
    if (system(cmd) != 0) {
        return -1;
    }
    char path[512];
    snprintf(path, sizeof(path), "%s/publish-seq.json", ledger_dir);
    int seq = 0;
    FILE *f = fopen(path, "r");
    if (f) {
        char buf[512];
        fread(buf, 1, sizeof(buf) - 1, f);
        buf[sizeof(buf) - 1] = '\0';
        fclose(f);
        const char *gp = strstr(buf, "\"graph_id\"");
        if (gp && strstr(gp, graph_id)) {
            const char *sp = strstr(buf, "publish_seq");
            if (sp) {
                seq = (int)strtod(strchr(sp, ':') + 1, NULL);
            }
        }
    }
    f = fopen(path, "w");
    if (!f) {
        return -1;
    }
    fprintf(
        f,
        "{\"graph_id\":\"%s\",\"publish_seq\":%d,\"witness_digest\":\"%s\"}\n",
        graph_id,
        seq + 1,
        witness_hex
    );
    fclose(f);
    return 0;
}
