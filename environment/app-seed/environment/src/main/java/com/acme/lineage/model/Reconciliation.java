package com.acme.lineage.model;

import java.util.ArrayList;
import java.util.List;

public final class Reconciliation {
    public static final class NodeOut {
        public final String runUid;
        public final String featurePath;
        public NodeOut(String runUid, String featurePath) {
            this.runUid = runUid;
            this.featurePath = featurePath;
        }
    }

    public static final class EdgeOut {
        public final String parent;
        public final String child;
        public final String annotation;
        public final String baseline;   // nullable
        public final String aucDelta;   // nullable
        public EdgeOut(String parent, String child, String annotation, String baseline, String aucDelta) {
            this.parent = parent;
            this.child = child;
            this.annotation = annotation;
            this.baseline = baseline;
            this.aucDelta = aucDelta;
        }
    }

    public static final class Diff {
        public final String kind;
        public final String runUid; // nullable
        public final String edge;   // nullable
        public final List<String> values;
        public Diff(String kind, String runUid, String edge, List<String> values) {
            this.kind = kind;
            this.runUid = runUid;
            this.edge = edge;
            this.values = values;
        }
    }

    public final List<NodeOut> nodes = new ArrayList<>();
    public final List<EdgeOut> edges = new ArrayList<>();
    public final List<Diff> representationDiffs = new ArrayList<>();
    public final List<Diff> semanticDiffs = new ArrayList<>();
}
