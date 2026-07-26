package com.acme.lineage.normalize;

import com.acme.lineage.model.RunRecord;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class AucDeltaCalculator {
    private final Map<String, RunRecord> runs;
    private final Map<String, List<String>> parents;

    public AucDeltaCalculator(Map<String, RunRecord> runs, Map<String, List<String>> parents) {
        this.runs = runs;
        this.parents = parents;
    }

    // FIXED: nearest released ancestor with the same evaluation cohort, searched
    // upward from the edge parent (distance 1). Returns null when none exists.
    public String baseline(String child, String edgeParent) {
        String cohort = runs.get(child).evaluationCohort;
        List<String> frontier = new ArrayList<>();
        frontier.add(edgeParent);
        Set<String> seen = new HashSet<>();
        while (!frontier.isEmpty()) {
            Collections.sort(frontier);
            List<String> nextF = new ArrayList<>();
            for (String nid : frontier) {
                if (!seen.add(nid)) continue;
                RunRecord r = runs.get(nid);
                if (r == null) continue;
                if ("released".equals(r.releaseStatus) && cohort.equals(r.evaluationCohort)) {
                    return nid;
                }
                for (String p : parents.getOrDefault(nid, Collections.emptyList())) {
                    if (!seen.contains(p)) nextF.add(p);
                }
            }
            frontier = nextF;
        }
        return null;
    }

    // FIXED: exact decimal arithmetic quantized to six places, HALF_EVEN.
    public String delta(String child, String baseline) {
        BigDecimal c = new BigDecimal(runs.get(child).auc);
        BigDecimal b = new BigDecimal(runs.get(baseline).auc);
        return c.subtract(b).setScale(6, RoundingMode.HALF_EVEN).toPlainString();
    }
}
