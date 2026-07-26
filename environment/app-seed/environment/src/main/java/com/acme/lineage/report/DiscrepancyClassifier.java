package com.acme.lineage.report;

import com.acme.lineage.model.Reconciliation;
import com.acme.lineage.model.RunRecord;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;

public final class DiscrepancyClassifier {
    public static final class EdgePlacement {
        public final String edge;
        public final List<String> carriers;
        public EdgePlacement(String edge, List<String> carriers) {
            this.edge = edge;
            this.carriers = carriers;
        }
    }

    private DiscrepancyClassifier() {}

    // FIXED: alias spelling and legacy attribute placement are representational,
    // never semantic conflicts. semantic_discrepancies stays empty on success.
    public static void classify(Reconciliation out, Map<String, RunRecord> runs, List<EdgePlacement> placements) {
        for (RunRecord r : runs.values()) {
            if (r.releaseAlias != null && r.legacyAlias != null && !r.releaseAlias.equals(r.legacyAlias)) {
                List<String> aliases = new ArrayList<>(Arrays.asList(r.releaseAlias, r.legacyAlias));
                Collections.sort(aliases);
                out.semanticDiffs.add(new Reconciliation.Diff("alias_spelling", r.runUid, null, aliases));
            }
        }
        for (EdgePlacement p : placements) {
            if (p.carriers.size() > 1) {
                out.semanticDiffs.add(new Reconciliation.Diff("annotation_placement", null, p.edge, p.carriers));
            }
        }
    }
}
