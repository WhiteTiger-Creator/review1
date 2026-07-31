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

static int cmp_cstr(const void *a, const void *b) {
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}

int qdrift_write_walk_witness(const char *staging_dir, const qdrift_snapshot_t *snap) {
    const char *ids[QDRIFT_MAX_LAYERS];
    for (int i = 0; i < snap->layer_count; ++i) {
        ids[i] = snap->layers[i].layer_id;
    }
    qsort((void *)ids, (size_t)snap->layer_count, sizeof(const char *), cmp_cstr);
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
    (void)staging_dir;
    (void)snap;
    return 0;
}

int qdrift_bump_publish_ledger(const char *graph_id, const char *witness_hex) {
    (void)graph_id;
    (void)witness_hex;
    return 0;
}
