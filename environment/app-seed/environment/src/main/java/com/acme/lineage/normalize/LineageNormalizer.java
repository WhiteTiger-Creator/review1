package com.acme.lineage.normalize;

import com.acme.lineage.cli.ExitCodes;
import com.acme.lineage.dot.DotGraph;
import com.acme.lineage.git.WorktreeReader;
import com.acme.lineage.ledger.RunIndex;
import com.acme.lineage.model.Reconciliation;
import com.acme.lineage.model.RunRecord;
import com.acme.lineage.policy.AnnotationPolicy;
import com.acme.lineage.report.DiscrepancyClassifier;
import com.acme.lineage.util.AuditException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public final class LineageNormalizer {
    private final RunIndex index;
    private final CanonicalIdResolver resolver;
    private final AnnotationPolicy annotationPolicy;
    private final boolean acceptLegacyAttrs;

    public LineageNormalizer(RunIndex index, boolean acceptLegacyAttrs) {
        this.index = index;
        this.resolver = new CanonicalIdResolver(index);
        this.annotationPolicy = new AnnotationPolicy();
        this.acceptLegacyAttrs = acceptLegacyAttrs;
    }

    private static final class ResolvedEdge {
        final String parent;
        final String child;
        final List<AnnotationPolicy.Candidate> candidates = new ArrayList<>();
        final Set<String> carriers = new TreeSet<>();
        ResolvedEdge(String parent, String child) { this.parent = parent; this.child = child; }
    }

    public Reconciliation normalize(WorktreeReader left, WorktreeReader right) {
        Map<String, ResolvedEdge> leftEdges = resolveEdges(left.graph);
        Map<String, ResolvedEdge> rightEdges = resolveEdges(right.graph);

        if (!leftEdges.keySet().equals(rightEdges.keySet())) {
            throw new AuditException(ExitCodes.CONFLICT, "CONFLICTING_PARENTAGE",
                "worktrees disagree on logical parentage");
        }
        checkMetricConflict(left.graph, right.graph);

        Map<String, ResolvedEdge> merged = new TreeMap<>();
        mergeInto(merged, leftEdges);
        mergeInto(merged, rightEdges);

        Set<String> uids = new TreeSet<>();
        for (ResolvedEdge e : merged.values()) { uids.add(e.parent); uids.add(e.child); }
        uids.addAll(resolveNodes(left.graph));
        uids.addAll(resolveNodes(right.graph));

        Map<String, RunRecord> runs = new LinkedHashMap<>();
        for (String uid : uids) {
            RunRecord r = index.byUid(uid);
            if (r == null) throw new AuditException(ExitCodes.VALIDATION, "UNKNOWN_RUN", "unknown run: " + uid);
            runs.put(uid, r);
        }

        Map<String, List<String>> parents = new HashMap<>();
        for (ResolvedEdge e : merged.values()) {
            parents.computeIfAbsent(e.child, k -> new ArrayList<>()).add(e.parent);
        }
        for (List<String> v : parents.values()) Collections.sort(v);

        FeaturePathBuilder fpb = new FeaturePathBuilder(runs, parents);
        AucDeltaCalculator auc = new AucDeltaCalculator(runs, parents);

        Reconciliation out = new Reconciliation();
        for (String uid : uids) out.nodes.add(new Reconciliation.NodeOut(uid, fpb.path(uid)));

        List<DiscrepancyClassifier.EdgePlacement> placements = new ArrayList<>();
        for (ResolvedEdge e : merged.values()) {
            String annotation = annotationPolicy.resolve(e.candidates);
            String baseline = auc.baseline(e.child, e.parent);
            String delta = (baseline == null) ? null : auc.delta(e.child, baseline);
            out.edges.add(new Reconciliation.EdgeOut(e.parent, e.child, annotation, baseline, delta));
            placements.add(new DiscrepancyClassifier.EdgePlacement(
                e.parent + ">" + e.child, new ArrayList<>(e.carriers)));
        }
        out.edges.sort(Comparator.comparing((Reconciliation.EdgeOut x) -> x.parent).thenComparing(x -> x.child));

        DiscrepancyClassifier.classify(out, runs, placements);
        return out;
    }

    private void mergeInto(Map<String, ResolvedEdge> merged, Map<String, ResolvedEdge> src) {
        for (Map.Entry<String, ResolvedEdge> e : src.entrySet()) {
            ResolvedEdge m = merged.computeIfAbsent(e.getKey(),
                k -> new ResolvedEdge(e.getValue().parent, e.getValue().child));
            m.candidates.addAll(e.getValue().candidates);
            m.carriers.addAll(e.getValue().carriers);
        }
    }

    private Set<String> resolveNodes(DotGraph g) {
        Set<String> uids = new TreeSet<>();
        for (String id : g.nodes.keySet()) uids.add(resolver.resolve(id));
        return uids;
    }

    private Map<String, ResolvedEdge> resolveEdges(DotGraph g) {
        Map<String, ResolvedEdge> res = new TreeMap<>();
        for (DotGraph.Edge e : g.edges) {
            String p = resolver.resolve(e.src);
            String c = resolver.resolve(e.dst);
            String key = p + "\u0000" + c;
            ResolvedEdge re = res.computeIfAbsent(key, k -> new ResolvedEdge(p, c));
            for (DotGraph.Attr a : e.attrs) {
                boolean isLabel = a.key.equals("label");
                boolean isLegacy = a.key.equals("xlabel") || a.key.equals("taillabel");
                if (isLabel || (isLegacy && acceptLegacyAttrs)) {
                    AnnotationPolicy.Candidate cand = AnnotationPolicy.Candidate.parse(a.value);
                    if (cand != null) {
                        re.candidates.add(cand);
                        re.carriers.add(a.key);
                    }
                }
            }
        }
        return res;
    }

    private void checkMetricConflict(DotGraph left, DotGraph right) {
        Map<String, String> la = nodeAuc(left);
        Map<String, String> ra = nodeAuc(right);
        for (Map.Entry<String, String> e : la.entrySet()) {
            String rv = ra.get(e.getKey());
            if (rv != null && !rv.equals(e.getValue())) {
                throw new AuditException(ExitCodes.CONFLICT, "CONFLICTING_METRICS",
                    "incompatible metric evidence for " + e.getKey());
            }
        }
    }

    private Map<String, String> nodeAuc(DotGraph g) {
        Map<String, String> m = new HashMap<>();
        for (DotGraph.Node n : g.nodes.values()) {
            for (DotGraph.Attr a : n.attrs) {
                if (a.key.equals("auc")) m.put(resolver.resolve(n.id), a.value);
            }
        }
        return m;
    }
}
