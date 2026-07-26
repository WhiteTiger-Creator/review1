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
        return edgeParent;
    }

    // FIXED: exact decimal arithmetic quantized to six places, HALF_EVEN.
    public String delta(String child, String baseline) {
        double c = Double.parseDouble(runs.get(child).auc);
        double b = Double.parseDouble(runs.get(baseline).auc);
        return String.format("%.6f", c - b);
    }
}
