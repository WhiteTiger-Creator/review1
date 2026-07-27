#include "ship_api.h"

#include <string.h>

SnapRef rank_pick(const SnapRef *cands, int n, const LedgerView *view) {
    SnapRef empty;
    memset(&empty, 0, sizeof(empty));
    if (n <= 0) {
        return empty;
    }
    (void)view;
    SnapRef best = cands[0];
    for (int i = 1; i < n; i++) {
        if (cands[i].mtime > best.mtime ||
            (cands[i].mtime == best.mtime && strcmp(cands[i].id, best.id) > 0)) {
            best = cands[i];
        }
    }
    return best;
}
