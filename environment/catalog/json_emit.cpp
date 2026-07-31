#include "qdrift/cert_json.h"

#include <openssl/evp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void qdrift_report_digest(const qdrift_cert_report_t *report, char *hex_out, int hex_len) {
    char buf[4096];
    int pos = snprintf(buf, sizeof(buf), "%s%s", report->graph_id, report->scenario_id);
    for (int i = 0; i < report->violation_count; ++i) {
        pos += snprintf(
            buf + pos,
            sizeof(buf) - (size_t)pos,
            "%s%.6f",
            report->violations[i].layer_id,
            report->violations[i].measured_drift
        );
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

int qdrift_write_cert_report(const qdrift_cert_report_t *report, const char *path) {
    FILE *f = fopen(path, "w");
    if (!f) {
        return -1;
    }
    char digest[65];
    qdrift_report_digest(report, digest, sizeof(digest));
    fprintf(f, "{\n");
    fprintf(f, "  \"graph_id\": \"%s\",\n", report->graph_id);
    fprintf(f, "  \"variant_id\": \"%s\",\n", report->variant_id);
    fprintf(f, "  \"scenario_id\": \"%s\",\n", report->scenario_id);
    fprintf(f, "  \"drift_bound\": %.6f,\n", report->drift_bound);
    fprintf(f, "  \"certified\": %s,\n", report->certified ? "true" : "false");
    fprintf(f, "  \"violations\": [\n");
    for (int i = 0; i < report->violation_count; ++i) {
        fprintf(
            f,
            "    {\"layer_id\": \"%s\", \"measured_drift\": %.6f, \"bound\": %.6f}%s\n",
            report->violations[i].layer_id,
            report->violations[i].measured_drift,
            report->violations[i].bound,
            i + 1 < report->violation_count ? "," : ""
        );
    }
    fprintf(f, "  ],\n");
    fprintf(f, "  \"digest\": \"%s\"\n", digest);
    fprintf(f, "}\n");
    fclose(f);
    return 0;
}
