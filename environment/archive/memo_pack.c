#include "ship_api.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

int memo_pack(const char *case_id, const char *selected_id, const char *note_text,
              const char *sha_prefix, const char *pack_label, const char *archive_root) {
    (void)selected_id;
    (void)note_text;
    (void)sha_prefix;
    if (!case_id || !case_id[0]) {
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
            "\"\",\n      \"note_text\": \"\",\n      \"sha_prefix\": \"\",\n      "
            "\"pack_label\": \"%s\"\n    }\n  ]\n}\n",
            case_id, pack_label ? pack_label : "");
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
