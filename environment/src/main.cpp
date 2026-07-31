#include <stdio.h>
#include <string.h>

int qdrift_cmd_load_graph(
    const char *graph_root,
    const char *graph_id,
    const char *variant_root,
    const char *variant_id,
    const char *scenario_root,
    const char *scenario_id
);
int qdrift_cmd_propagate(const char *graph_id);
int qdrift_cmd_certify(const char *graph_id);

static int streq(const char *a, const char *b) {
    return strcmp(a, b) == 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return 1;
    }
    if (streq(argv[1], "ingest-pack")) {
        const char *graph_root = "/app/fixtures/static-graphs";
        const char *graph_id = "";
        const char *variant_root = "/app/fixtures/quant-variants";
        const char *variant_id = "";
        const char *scenario_root = "/app/fixtures/drift-scenarios";
        const char *scenario_id = "";
        for (int i = 2; i < argc - 1; i += 2) {
            if (streq(argv[i], "--graph-root")) {
                graph_root = argv[i + 1];
            } else if (streq(argv[i], "--graph")) {
                graph_id = argv[i + 1];
            } else if (streq(argv[i], "--variant-root")) {
                variant_root = argv[i + 1];
            } else if (streq(argv[i], "--variant")) {
                variant_id = argv[i + 1];
            } else if (streq(argv[i], "--scenario-root")) {
                scenario_root = argv[i + 1];
            } else if (streq(argv[i], "--scenario")) {
                scenario_id = argv[i + 1];
            }
        }
        return qdrift_cmd_load_graph(
            graph_root, graph_id, variant_root, variant_id, scenario_root, scenario_id
        );
    }
    if (streq(argv[1], "walk-intervals")) {
        const char *graph_id = "";
        for (int i = 2; i < argc - 1; i += 2) {
            if (streq(argv[i], "--graph")) {
                graph_id = argv[i + 1];
            }
        }
        return qdrift_cmd_propagate(graph_id);
    }
    if (streq(argv[1], "publish-report")) {
        const char *graph_id = "";
        for (int i = 2; i < argc - 1; i += 2) {
            if (streq(argv[i], "--graph")) {
                graph_id = argv[i + 1];
            }
        }
        return qdrift_cmd_certify(graph_id);
    }
    if (streq(argv[1], "smoke-publish")) {
        qdrift_cmd_load_graph(
            "/app/fixtures/static-graphs",
            "linear-clean",
            "/app/fixtures/quant-variants",
            "v-int8-tight",
            "/app/fixtures/drift-scenarios",
            "scenario-tight"
        );
        qdrift_cmd_propagate("linear-clean");
        return qdrift_cmd_certify("linear-clean");
    }
    return 1;
}
