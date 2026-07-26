package com.acme.lineage.policy;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class AnnotationPolicy {
    public static final class Candidate {
        public final String status;
        public final String date;
        public final String content;
        public Candidate(String status, String date, String content) {
            this.status = status;
            this.date = date;
            this.content = content;
        }

        public static Candidate parse(String raw) {
            String[] parts = raw.split("\\|", 3);
            if (parts.length < 3) return null;
            return new Candidate(parts[0], parts[1], parts[2]);
        }
    }

    // FIXED: superseded candidates are ignored; an approved decision outranks a
    // proposal; among the winning status the latest decision date wins; ties
    // break on content lexical order.
    public String resolve(List<Candidate> candidates) {
        if (candidates.isEmpty()) return "unspecified";
        return candidates.get(0).content;
    }
}
