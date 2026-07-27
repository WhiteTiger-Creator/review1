#define _POSIX_C_SOURCE 200809L
#include "screening_gate.h"
#include <errno.h>
#include <math.h>
#include <sqlite3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

typedef struct {
    char frame_id[128];
    double edge_density;
    double skin_ratio;
    double text_ratio;
    int label;
    double score;
    int prediction;
} Row;

static void trim(char *s) {
    size_t n = strlen(s);
    while (n > 0 && (s[n - 1] == '\n' || s[n - 1] == '\r' || s[n - 1] == ' ')) s[--n] = '\0';
}

static int run_capture(const char *cmd, char *out, size_t cap) {
    FILE *p = popen(cmd, "r");
    if (!p) return -1;
    size_t used = 0;
    while (used + 1 < cap) {
        size_t got = fread(out + used, 1, cap - used - 1, p);
        used += got;
        if (got == 0) break;
    }
    out[used] = '\0';
    int rc = pclose(p);
    trim(out);
    if (rc == -1 || !WIFEXITED(rc)) return -1;
    return WEXITSTATUS(rc);
}

static int jq_value(const char *path, const char *expr, char *out, size_t cap) {
    char cmd[2048];
    if (snprintf(cmd, sizeof(cmd), "jq -er '%s' '%s' 2>/dev/null", expr, path) >= (int)sizeof(cmd)) return -1;
    return run_capture(cmd, out, cap);
}

static int file_sha256(const char *path, char *out, size_t cap) {
    char cmd[2048];
    if (snprintf(cmd, sizeof(cmd), "sha256sum '%s' | awk '{print $1}'", path) >= (int)sizeof(cmd)) return -1;
    return run_capture(cmd, out, cap);
}

static int verify_signature(const char *pub, const char *sig, const char *policy) {
    char cmd[4096], out[256];
    if (snprintf(cmd, sizeof(cmd), "openssl dgst -sha256 -verify '%s' -signature '%s' '%s' >/dev/null 2>&1", pub, sig, policy) >= (int)sizeof(cmd)) return 0;
    return run_capture(cmd, out, sizeof(out)) == 0;
}

static int write_error(const char *output, const char *code) {
    FILE *fp = fopen(output, "w");
    if (!fp) return 2;
    fprintf(fp, "{\"error\":\"%s\"}\n", code);
    fclose(fp);
    return 1;
}

static int load_rows(sqlite3 *db, Row *rows, int *count) {
    const char *sql = "SELECT frame_id,edge_density,skin_ratio,text_ratio,label FROM image_features ORDER BY frame_id";
    sqlite3_stmt *stmt = NULL;
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, NULL) != SQLITE_OK) return 0;
    int n = 0;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        if (n >= MAX_ROWS) { sqlite3_finalize(stmt); return 0; }
        const unsigned char *id = sqlite3_column_text(stmt, 0);
        snprintf(rows[n].frame_id, sizeof(rows[n].frame_id), "%s", id ? (const char *)id : "");
        rows[n].edge_density = sqlite3_column_double(stmt, 1);
        rows[n].skin_ratio = sqlite3_column_double(stmt, 2);
        rows[n].text_ratio = sqlite3_column_double(stmt, 3);
        rows[n].label = sqlite3_column_int(stmt, 4);
        n++;
    }
    sqlite3_finalize(stmt);
    *count = n;
    return n > 0;
}

static int signer_state(sqlite3 *db, const char *signer, char *key_sha, size_t cap, char *status, size_t sc) {
    sqlite3_stmt *stmt = NULL;
    const char *sql = "SELECT public_key_sha256,status FROM trusted_signers WHERE signer_id=?1";
    if (sqlite3_prepare_v2(db, sql, -1, &stmt, NULL) != SQLITE_OK) return 0;
    sqlite3_bind_text(stmt, 1, signer, -1, SQLITE_TRANSIENT);
    int ok = 0;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        snprintf(key_sha, cap, "%s", sqlite3_column_text(stmt, 0));
        snprintf(status, sc, "%s", sqlite3_column_text(stmt, 1));
        ok = 1;
    }
    sqlite3_finalize(stmt);
    return ok;
}

int main(int argc, char **argv) {
    const char *policy = "/app/trust/release-policy.json";
    const char *signature = "/app/trust/release-policy.sig";
    const char *pubkey = "/app/trust/release.pub";
    const char *model = "/app/model/metadata.json";
    const char *config = "/app/config/screening.json";
    const char *db_path = "/app/data/features.db";
    const char *output = "/app/output/gate.json";
    for (int i = 1; i + 1 < argc; i += 2) {
        if (strcmp(argv[i], "--policy") == 0) policy = argv[i + 1];
        else if (strcmp(argv[i], "--signature") == 0) signature = argv[i + 1];
        else if (strcmp(argv[i], "--public-key") == 0) pubkey = argv[i + 1];
        else if (strcmp(argv[i], "--model") == 0) model = argv[i + 1];
        else if (strcmp(argv[i], "--config") == 0) config = argv[i + 1];
        else if (strcmp(argv[i], "--db") == 0) db_path = argv[i + 1];
        else if (strcmp(argv[i], "--output") == 0) output = argv[i + 1];
        else return 2;
    }

    if (!verify_signature(pubkey, signature, policy)) return write_error(output, "signature_invalid");

    char signer[256], policy_model_sha[128], allowed_kind[128];
    char min_s[64], max_s[64], model_sha[128], pub_sha[128];
    if (jq_value(policy, ".signer_id", signer, sizeof(signer)) != 0 ||
        jq_value(policy, ".model_sha256", policy_model_sha, sizeof(policy_model_sha)) != 0 ||
        jq_value(policy, ".allowed_model_kind", allowed_kind, sizeof(allowed_kind)) != 0 ||
        jq_value(policy, ".minimum_threshold", min_s, sizeof(min_s)) != 0 ||
        jq_value(policy, ".maximum_threshold", max_s, sizeof(max_s)) != 0)
        return write_error(output, "policy_invalid");
    if (file_sha256(model, model_sha, sizeof(model_sha)) != 0 || strcmp(model_sha, policy_model_sha) != 0)
        return write_error(output, "model_digest_mismatch");
    if (file_sha256(pubkey, pub_sha, sizeof(pub_sha)) != 0) return write_error(output, "public_key_invalid");

    char kind[128], threshold_s[64], profile[128], weights_s[256], bias_s[64];
    if (jq_value(model, ".kind", kind, sizeof(kind)) != 0 || strcmp(kind, allowed_kind) != 0)
        return write_error(output, "model_kind_rejected");
    if (jq_value(config, ".threshold", threshold_s, sizeof(threshold_s)) != 0 ||
        jq_value(config, ".profile", profile, sizeof(profile)) != 0 ||
        jq_value(model, ".weights | @csv", weights_s, sizeof(weights_s)) != 0 ||
        jq_value(model, ".bias", bias_s, sizeof(bias_s)) != 0)
        return write_error(output, "configuration_invalid");
    double threshold = strtod(threshold_s, NULL), min_t = strtod(min_s, NULL), max_t = strtod(max_s, NULL);
    if (!(threshold >= min_t && threshold <= max_t)) return write_error(output, "threshold_rejected");

    double w[3], bias = strtod(bias_s, NULL);
    if (sscanf(weights_s, "\"%lf,%lf,%lf\"", &w[0], &w[1], &w[2]) != 3 &&
        sscanf(weights_s, "%lf,%lf,%lf", &w[0], &w[1], &w[2]) != 3)
        return write_error(output, "model_weights_invalid");

    sqlite3 *db = NULL;
    if (sqlite3_open_v2(db_path, &db, SQLITE_OPEN_READONLY, NULL) != SQLITE_OK) return write_error(output, "database_unavailable");
    char db_key_sha[128], status[64];
    if (!signer_state(db, signer, db_key_sha, sizeof(db_key_sha), status, sizeof(status))) {
        sqlite3_close(db); return write_error(output, "signer_unknown");
    }
    if (strcmp(status, "trusted") != 0) { sqlite3_close(db); return write_error(output, "signer_revoked"); }
    if (strcmp(db_key_sha, pub_sha) != 0) { sqlite3_close(db); return write_error(output, "signer_key_mismatch"); }

    Row rows[MAX_ROWS]; int n = 0;
    if (!load_rows(db, rows, &n)) { sqlite3_close(db); return write_error(output, "evidence_unavailable"); }
    sqlite3_close(db);

    int tp=0, tn=0, fp=0, fn=0, quarantined=0;
    for (int i=0;i<n;i++) {
        double z = bias + w[0]*rows[i].edge_density + w[1]*rows[i].skin_ratio + w[2]*rows[i].text_ratio;
        rows[i].score = 1.0 / (1.0 + exp(-z));
        rows[i].prediction = rows[i].score >= threshold ? 1 : 0;
        if (rows[i].prediction) quarantined++;
        if (rows[i].prediction==1 && rows[i].label==1) tp++;
        else if (rows[i].prediction==0 && rows[i].label==0) tn++;
        else if (rows[i].prediction==1) fp++;
        else fn++;
    }

    FILE *fpout = fopen(output, "w");
    if (!fpout) return 2;
    fprintf(fpout, "{\"gate\":{\"status\":\"admit\",\"quarantined\":%d},", quarantined);
    fprintf(fpout, "\"trust\":{\"signature_verified\":true,\"signer_id\":\"%s\",\"public_key_sha256\":\"%s\",\"model_sha256\":\"%s\"},", signer, pub_sha, model_sha);
    fprintf(fpout, "\"policy\":{\"profile\":\"%s\",\"threshold\":%.6f},\"decisions\":[", profile, threshold);
    for (int i=0;i<n;i++) {
        if (i) fputc(',', fpout);
        fprintf(fpout, "{\"frame_id\":\"%s\",\"score\":%.6f,\"action\":\"%s\",\"label\":%d}", rows[i].frame_id, rows[i].score, rows[i].prediction ? "quarantine" : "allow", rows[i].label);
    }
    fprintf(fpout, "],\"evidence\":{\"tp\":%d,\"tn\":%d,\"fp\":%d,\"fn\":%d,\"total\":%d}}\n", tp,tn,fp,fn,n);
    fclose(fpout);
    return 0;
}
