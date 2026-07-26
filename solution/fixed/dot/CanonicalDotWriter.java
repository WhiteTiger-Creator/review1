package com.acme.lineage.dot;

import com.acme.lineage.model.Reconciliation;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class CanonicalDotWriter {
    private CanonicalDotWriter() {}

    // FIXED: nodes sorted by run_uid, edges by (parent, child); full escaping.
    public static String write(Reconciliation r) {
        StringBuilder sb = new StringBuilder();
        sb.append("digraph Lineage {\n");
        sb.append("  graph [name=").append(q("reconciled-lineage")).append("];\n");

        List<Reconciliation.NodeOut> nodes = new ArrayList<>(r.nodes);
        nodes.sort(Comparator.comparing(n -> n.runUid));
        for (Reconciliation.NodeOut n : nodes) {
            sb.append("  ").append(q(n.runUid))
              .append(" [id=").append(q(n.runUid))
              .append(", label=").append(q(n.runUid))
              .append(", feature_path=").append(q(n.featurePath))
              .append("];\n");
        }

        List<Reconciliation.EdgeOut> edges = new ArrayList<>(r.edges);
        edges.sort(Comparator.comparing((Reconciliation.EdgeOut e) -> e.parent).thenComparing(e -> e.child));
        for (Reconciliation.EdgeOut e : edges) {
            sb.append("  ").append(q(e.parent)).append(" -> ").append(q(e.child))
              .append(" [annotation=").append(q(e.annotation));
            if (e.baseline != null) {
                sb.append(", auc_delta=").append(q(e.aucDelta))
                  .append(", baseline=").append(q(e.baseline));
            }
            sb.append("];\n");
        }
        sb.append("}\n");
        return sb.toString();
    }

    private static String q(String s) {
        return "\"" + DotEscaper.escape(s) + "\"";
    }
}
