#include "qdrift/bound_compare.h"
#include "qdrift/cert_json.h"
#include "qdrift/graph_model.h"
#include "qdrift/propagate_engine.h"
#include "qdrift/staging_io.h"
#include "qdrift/witness_seal.h"

#include <cstdlib>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static int ensure_dir(const char *path) {
    char cmd[512];
    snprintf(cmd, sizeof(cmd), "mkdir -p %s", path);
    return system(cmd);
}

int qdrift_cmd_load_graph(
    const char *graph_root,
    const char *graph_id,
    const char *variant_root,
    const char *variant_id,
    const char *scenario_root,
    const char *scenario_id
) {
    char pack_path[512];
    snprintf(pack_path, sizeof(pack_path), "%s/%s", graph_root, graph_id);
    qdrift_graph_t graph;
    if (qdrift_load_graph_pack(pack_path, &graph) != 0) {
        return 1;
    }
    if (qdrift_apply_variant(variant_root, variant_id, &graph) != 0) {
        return 1;
    }
    char staging[512];
    snprintf(staging, sizeof(staging), "/app/var/qbound-interval-store/%s", graph_id);
    ensure_dir(staging);
    char cmd[1024];
    snprintf(cmd, sizeof(cmd), "cp %s/graph.json %s/weights.json %s/", pack_path, pack_path, staging);
    if (system(cmd) != 0) {
        return 1;
    }
    snprintf(cmd, sizeof(cmd), "cp %s/%s/scenario.json %s/scenario.json", scenario_root, scenario_id, staging);
    if (system(cmd) != 0) {
        return 1;
    }
    snprintf(
        cmd,
        sizeof(cmd),
        "cp %s/%s/variant.json %s/variant.json",
        variant_root,
        variant_id,
        staging
    );
    if (system(cmd) != 0) {
        return 1;
    }
    qdrift_write_pack_context(staging, graph_id, variant_id, scenario_id, graph.certification_epoch);
    fprintf(stderr, "QBOUND_INGEST_OK\n");
    return 0;
}

int qdrift_cmd_propagate(const char *graph_id) {
    char staging[512];
    snprintf(staging, sizeof(staging), "/app/var/qbound-interval-store/%s", graph_id);
    char pack_context_path[560];
    snprintf(pack_context_path, sizeof(pack_context_path), "%s/pack-context.json", staging);
    FILE *mf = fopen(pack_context_path, "r");
    if (!mf) {
        return 1;
    }
    char mbuf[512];
    fread(mbuf, 1, sizeof(mbuf) - 1, mf);
    mbuf[sizeof(mbuf) - 1] = '\0';
    fclose(mf);

    char variant_id[64] = {0};
    char scenario_id[64] = {0};
    const char *vp = strstr(mbuf, "\"variant_id\"");
    if (vp) {
        vp = strchr(vp, ':');
        vp = strchr(vp, '"') + 1;
        const char *ve = strchr(vp, '"');
        int n = (int)(ve - vp);
        memcpy(variant_id, vp, (size_t)n);
    }
    const char *sp = strstr(mbuf, "\"scenario_id\"");
    if (sp) {
        sp = strchr(sp, ':');
        sp = strchr(sp, '"') + 1;
        const char *se = strchr(sp, '"');
        int n = (int)(se - sp);
        memcpy(scenario_id, sp, (size_t)n);
    }

    char pack_path[512];
    snprintf(pack_path, sizeof(pack_path), "%s", staging);
    qdrift_graph_t graph;
    if (qdrift_load_graph_pack(pack_path, &graph) != 0) {
        return 1;
    }
    char variant_path[560];
    snprintf(variant_path, sizeof(variant_path), "%s/variant.json", staging);
    if (qdrift_apply_variant_file(variant_path, &graph) != 0) {
        snprintf(pack_path, sizeof(pack_path), "/app/fixtures/quant-variants");
        if (qdrift_apply_variant(pack_path, variant_id, &graph) != 0) {
            return 1;
        }
    }
    qdrift_scenario_t scenario;
    char scenario_path[560];
    snprintf(scenario_path, sizeof(scenario_path), "%s/scenario.json", staging);
    if (qdrift_load_scenario_file(scenario_path, &scenario) != 0) {
        snprintf(pack_path, sizeof(pack_path), "/app/fixtures/drift-scenarios");
        if (qdrift_load_scenario(pack_path, scenario_id, &scenario) != 0) {
            return 1;
        }
    }

    qdrift_snapshot_t snap;
    if (qdrift_run_propagation(&graph, &scenario, variant_id, &snap) != 0) {
        return 1;
    }
    qdrift_write_snapshot(staging, &snap);
    if (qdrift_write_walk_witness(staging, &snap) != 0) {
        return 1;
    }
    fprintf(stderr, "QBOUND_WALK_OK\n");
    return 0;
}

int qdrift_cmd_certify(const char *graph_id) {
    char staging[512];
    snprintf(staging, sizeof(staging), "/app/var/qbound-interval-store/%s", graph_id);
    qdrift_snapshot_t snap;
    if (qdrift_read_snapshot(staging, &snap) != 0) {
        return 1;
    }
    if (qdrift_validate_walk_witness(staging, &snap) != 0) {
        return 1;
    }
    char pack_context_path[560];
    snprintf(pack_context_path, sizeof(pack_context_path), "%s/pack-context.json", staging);
    FILE *mf = fopen(pack_context_path, "r");
    char mbuf[512] = {0};
    if (mf) {
        fread(mbuf, 1, sizeof(mbuf) - 1, mf);
        fclose(mf);
    }
    int epoch = 0;
    const char *ep = strstr(mbuf, "certification_epoch");
    if (ep) {
        epoch = (int)strtod(strchr(ep, ':') + 1, NULL);
    }
    qdrift_scenario_t scenario;
    char scenario_path[560];
    snprintf(scenario_path, sizeof(scenario_path), "%s/scenario.json", staging);
    if (qdrift_load_scenario_file(scenario_path, &scenario) != 0) {
        if (qdrift_load_scenario("/app/fixtures/drift-scenarios", snap.scenario_id, &scenario) != 0) {
            return 1;
        }
    }
    qdrift_cert_report_t report;
    qdrift_build_cert_report(&snap, &scenario, epoch, &report);
    ensure_dir("/app/output");
    if (qdrift_write_cert_report(&report, "/app/output/drift_certification_report.json") != 0) {
        return 1;
    }
    char witness_hex[65] = {0};
    char witness_path[560];
    snprintf(witness_path, sizeof(witness_path), "%s/walk-witness.json", staging);
    FILE *wf = fopen(witness_path, "r");
    if (wf) {
        char wbuf[256];
        fread(wbuf, 1, sizeof(wbuf) - 1, wf);
        wbuf[sizeof(wbuf) - 1] = '\0';
        fclose(wf);
        const char *dp = strstr(wbuf, "layer_order_digest");
        if (dp) {
            dp = strchr(dp, ':');
            if (dp) {
                dp = strchr(dp, '"');
                if (dp) {
                    dp++;
                    const char *de = strchr(dp, '"');
                    if (de) {
                        int n = (int)(de - dp);
                        if (n >= (int)sizeof(witness_hex)) {
                            n = (int)sizeof(witness_hex) - 1;
                        }
                        memcpy(witness_hex, dp, (size_t)n);
                        witness_hex[n] = '\0';
                    }
                }
            }
        }
    }
    if (qdrift_bump_publish_ledger(graph_id, witness_hex) != 0) {
        return 1;
    }
    fprintf(stderr, "QBOUND_PUBLISH_OK\n");
    return 0;
}
