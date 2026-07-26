package com.acme.lineage.normalize;

import com.acme.lineage.cli.ExitCodes;
import com.acme.lineage.ledger.RunIndex;
import com.acme.lineage.util.AuditException;
import java.util.Set;

public final class CanonicalIdResolver {
    private final RunIndex index;

    public CanonicalIdResolver(RunIndex index) { this.index = index; }

    // FIXED: resolve every branch-local id to the ledger's stable run_uid,
    // rejecting aliases that map to more than one run.
    public String resolve(String localId) {
        if (index.hasUid(localId)) {
            return localId;
        }
        Set<String> uids = index.uidsForAlias(localId);
        if (uids.isEmpty()) {
            throw new AuditException(ExitCodes.VALIDATION, "UNKNOWN_RUN", "unknown run for id: " + localId);
        }
        if (uids.size() > 1) {
            throw new AuditException(ExitCodes.VALIDATION, "AMBIGUOUS_ALIAS",
                "ambiguous alias " + localId + " resolves to " + uids);
        }
        return uids.iterator().next();
    }
}
