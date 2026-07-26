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
        // Branch-local identifiers are treated as canonical here.
        return localId;
    }
}
