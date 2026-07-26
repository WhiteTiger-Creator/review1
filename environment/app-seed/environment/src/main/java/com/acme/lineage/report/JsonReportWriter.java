package com.acme.lineage.report;

import com.acme.lineage.model.Reconciliation;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class JsonReportWriter {
    private JsonReportWriter() {}

    public static String write(Reconciliation r) {
        List<Reconciliation.Diff> reps = new ArrayList<>(r.representationDiffs);
        reps.sort(Comparator
            .comparing((Reconciliation.Diff d) -> d.kind)
            .thenComparing(d -> d.runUid == null ? "" : d.runUid)
            .thenComparing(d -> d.edge == null ? "" : d.edge));
        List<Reconciliation.Diff> sem = new ArrayList<>(r.semanticDiffs);
        sem.sort(Comparator
            .comparing((Reconciliation.Diff d) -> d.kind)
            .thenComparing(d -> d.runUid == null ? "" : d.runUid)
            .thenComparing(d -> d.edge == null ? "" : d.edge));

        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"schema_version\":\"1.0\",");
        sb.append("\"node_count\":").append(r.nodes.size()).append(",");
        sb.append("\"edge_count\":").append(r.edges.size()).append(",");
        sb.append("\"representation_differences\":[");
        for (int i = 0; i < reps.size(); i++) {
            if (i > 0) sb.append(",");
            sb.append(diffJson(reps.get(i)));
        }
        sb.append("],");
        sb.append("\"semantic_discrepancies\":[");
        for (int i = 0; i < sem.size(); i++) {
            if (i > 0) sb.append(",");
            sb.append(diffJson(sem.get(i)));
        }
        sb.append("]}");
        sb.append("\n");
        return sb.toString();
    }

    private static String diffJson(Reconciliation.Diff d) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\"kind\":").append(str(d.kind));
        if (d.runUid != null) sb.append(",\"run_uid\":").append(str(d.runUid));
        if (d.edge != null) sb.append(",\"edge\":").append(str(d.edge));
        if ("alias_spelling".equals(d.kind)) {
            sb.append(",\"aliases\":").append(arr(d.values));
        } else {
            sb.append(",\"attributes\":").append(arr(d.values));
        }
        sb.append("}");
        return sb.toString();
    }

    private static String arr(List<String> v) {
        StringBuilder b = new StringBuilder("[");
        for (int i = 0; i < v.size(); i++) {
            if (i > 0) b.append(",");
            b.append(str(v.get(i)));
        }
        b.append("]");
        return b.toString();
    }

    private static String str(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '\\': b.append("\\\\"); break;
                case '"': b.append("\\\""); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        b.append("\"");
        return b.toString();
    }
}
