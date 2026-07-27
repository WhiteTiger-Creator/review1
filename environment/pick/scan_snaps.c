#include "ship_api.h"

#include <dirent.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static int tier_for(const LedgerView *view, const char *id) {
    for (int i = 0; i < view->n_entries; i++) {
        if (strcmp(view->entries[i].id, id) == 0) {
            return view->entries[i].tier;
        }
    }
    return 0;
}

int scan_snaps(const char *snaps_root, const LedgerView *view, SnapRef *out, int *n_out) {
    DIR *d = opendir(snaps_root);
    if (!d) {
        *n_out = 0;
        return -1;
    }
    int n = 0;
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL && n < SHIP_MAX_CANDS) {
        if (ent->d_name[0] == '.') {
            continue;
        }
        char path[SHIP_MAX_PATH];
        snprintf(path, sizeof(path), "%s/%s", snaps_root, ent->d_name);
        struct stat st;
        if (stat(path, &st) != 0 || !S_ISDIR(st.st_mode)) {
            continue;
        }
        char metrics[SHIP_MAX_PATH];
        snprintf(metrics, sizeof(metrics), "%s/metrics.json", path);
        struct stat mst;
        if (stat(metrics, &mst) != 0 || !S_ISREG(mst.st_mode)) {
            continue;
        }
        memset(&out[n], 0, sizeof(out[n]));
        snprintf(out[n].id, sizeof(out[n].id), "%s", ent->d_name);
        snprintf(out[n].path, sizeof(out[n].path), "%s", path);
        out[n].tier = tier_for(view, out[n].id);
        out[n].mtime = (double)mst.st_mtime;
        n++;
    }
    closedir(d);
    /* stable order for listing */
    for (int i = 0; i < n; i++) {
        for (int j = i + 1; j < n; j++) {
            if (strcmp(out[j].id, out[i].id) < 0) {
                SnapRef tmp = out[i];
                out[i] = out[j];
                out[j] = tmp;
            }
        }
    }
    *n_out = n;
    return 0;
}
