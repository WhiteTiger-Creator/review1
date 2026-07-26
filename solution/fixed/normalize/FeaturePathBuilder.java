package com.acme.lineage.normalize;

import com.acme.lineage.model.RunRecord;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class FeaturePathBuilder {
    private final Map<String, RunRecord> runs;
    private final Map<String, List<String>> parents;
    private final Map<String, String> memo = new HashMap<>();

    public FeaturePathBuilder(Map<String, RunRecord> runs, Map<String, List<String>> parents) {
        this.runs = runs;
        this.parents = parents;
    }

    public String path(String uid) {
        if (memo.containsKey(uid)) return memo.get(uid);
        List<String> ps = parents.getOrDefault(uid, Collections.emptyList());
        String result;
        if (ps.isEmpty()) {
            result = uid;
        } else if (ps.size() == 1) {
            String p = ps.get(0);
            if (featureChanging(uid, ps)) {
                result = path(p) + ">" + uid;
            } else {
                result = path(p);
            }
        } else {
            List<String> parentPaths = new ArrayList<>();
            for (String p : ps) parentPaths.add(path(p));
            Collections.sort(parentPaths);
            result = "[" + String.join("|", parentPaths) + "]>" + uid;
        }
        memo.put(uid, result);
        return result;
    }

    // FIXED: only a training stage with a changed feature-set hash, or an
    // ensemble stage, changes the feature set. Calibration and promotion
    // inherit the parent path unchanged.
    private boolean featureChanging(String uid, List<String> ps) {
        String stage = runs.get(uid).stageKind;
        if (ps.isEmpty()) return true;
        if ("ensemble".equals(stage)) return true;
        if ("train".equals(stage)) {
            for (String p : ps) {
                if (!runs.get(uid).featureSetHash.equals(runs.get(p).featureSetHash)) return true;
            }
            return false;
        }
        return false;
    }
}
