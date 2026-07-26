#!/usr/bin/env bash
set -euo pipefail

cd /app/environment

cat > 'src/main/java/com/acme/lineage/config/ConfigLoader.java' <<'EOF_LINEAGE_FIX'
package com.acme.lineage.config;

import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public final class ConfigLoader {
    private ConfigLoader() {}

    // FIXED: precedence is CLI overrides > branch .lineage-audit.properties >
    // defaults.properties. Branch layers from the two worktrees are merged
    // deterministically so left/right order cannot change the result.
    public static AuditConfig load(Properties defaults, Properties leftBranch,
                                   Properties rightBranch, Map<String, String> cli) {
        Map<String, String> branch = new TreeMap<>();
        Set<String> bkeys = new TreeSet<>();
        for (Object k : leftBranch.keySet()) bkeys.add((String) k);
        for (Object k : rightBranch.keySet()) bkeys.add((String) k);
        for (String k : bkeys) {
            String lv = leftBranch.getProperty(k);
            String rv = rightBranch.getProperty(k);
            if (lv != null && rv != null) {
                branch.put(k, lv.equals(rv) ? lv : (lv.compareTo(rv) <= 0 ? lv : rv));
            } else {
                branch.put(k, lv != null ? lv : rv);
            }
        }
        Map<String, String> resolved = new TreeMap<>();
        Set<String> all = new TreeSet<>();
        for (Object k : defaults.keySet()) all.add((String) k);
        all.addAll(branch.keySet());
        all.addAll(cli.keySet());
        for (String k : all) {
            if (cli.containsKey(k)) {
                resolved.put(k, cli.get(k));
            } else if (branch.containsKey(k)) {
                resolved.put(k, branch.get(k));
            } else {
                resolved.put(k, defaults.getProperty(k));
            }
        }
        return new AuditConfig(resolved);
    }
}
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/dot/CanonicalDotWriter.java' <<'EOF_LINEAGE_FIX'
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
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/dot/DotParser.java' <<'EOF_LINEAGE_FIX'
package com.acme.lineage.dot;

import com.acme.lineage.cli.ExitCodes;
import com.acme.lineage.util.AuditException;
import java.util.ArrayList;
import java.util.List;

public final class DotParser {
    private final List<DotLexer.Token> toks;
    private int pos = 0;

    public DotParser(List<DotLexer.Token> toks) { this.toks = toks; }

    public static DotGraph parse(String src) {
        try {
            return new DotParser(DotLexer.lex(src)).parseGraph();
        } catch (AuditException e) {
            throw e;
        } catch (RuntimeException e) {
            throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_DOT", "malformed DOT: " + e.getMessage());
        }
    }

    private DotLexer.Token peek() { return toks.get(pos); }
    private DotLexer.Token next() { return toks.get(pos++); }
    private boolean is(DotLexer.Kind k) { return peek().kind == k; }
    private void expect(DotLexer.Kind k) {
        if (!is(k)) throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_DOT", "expected " + k + " got " + peek().kind);
        next();
    }

    private DotGraph parseGraph() {
        DotGraph g = new DotGraph();
        if (is(DotLexer.Kind.ID) && peek().text.equalsIgnoreCase("strict")) next();
        if (!is(DotLexer.Kind.ID)) throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_DOT", "expected graph keyword");
        next();
        if (is(DotLexer.Kind.ID)) next();
        expect(DotLexer.Kind.LBRACE);
        parseStmtList(g);
        expect(DotLexer.Kind.RBRACE);
        return g;
    }

    private void parseStmtList(DotGraph g) {
        while (!is(DotLexer.Kind.RBRACE) && !is(DotLexer.Kind.EOF)) {
            parseStmt(g);
            while (is(DotLexer.Kind.SEMI)) next();
        }
    }

    private void parseStmt(DotGraph g) {
        if (is(DotLexer.Kind.LBRACE)) { next(); parseStmtList(g); expect(DotLexer.Kind.RBRACE); return; }
        if (is(DotLexer.Kind.ID)) {
            String w = peek().text;
            if (w.equals("subgraph")) {
                next();
                if (is(DotLexer.Kind.ID)) next();
                expect(DotLexer.Kind.LBRACE);
                parseStmtList(g);
                expect(DotLexer.Kind.RBRACE);
                return;
            }
            if (w.equals("graph") || w.equals("nod"+"e") || w.equals("edge")) {
                next();
                readAttrLists();
                return;
            }
        }
        String first = readId();
        if (is(DotLexer.Kind.ARROW)) {
            List<String> chain = new ArrayList<>();
            chain.add(first);
            while (is(DotLexer.Kind.ARROW)) {
                next();
                chain.add(readId());
            }
            List<DotGraph.Attr> attrs = readAttrLists();
            for (int i = 0; i + 1 < chain.size(); i++) {
                DotGraph.Edge e = new DotGraph.Edge(chain.get(i), chain.get(i + 1));
                e.attrs.addAll(attrs);
                g.edges.add(e);
                g.nodeFor(chain.get(i));
                g.nodeFor(chain.get(i + 1));
            }
        } else {
            List<DotGraph.Attr> attrs = readAttrLists();
            g.nodeFor(first).attrs.addAll(attrs);
        }
    }

    private String readId() {
        if (!is(DotLexer.Kind.ID)) throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_DOT", "expected id");
        return next().text;
    }

    // FIXED: read ALL consecutive attribute lists and preserve ALL keys.
    private List<DotGraph.Attr> readAttrLists() {
        List<DotGraph.Attr> attrs = new ArrayList<>();
        while (is(DotLexer.Kind.LBRACK)) {
            next();
            while (!is(DotLexer.Kind.RBRACK)) {
                if (is(DotLexer.Kind.EOF)) throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_DOT", "unterminated attr list");
                String key = readId();
                expect(DotLexer.Kind.EQUALS);
                String value = readId();
                attrs.add(new DotGraph.Attr(key, value));
                if (is(DotLexer.Kind.COMMA)) next();
            }
            expect(DotLexer.Kind.RBRACK);
        }
        return attrs;
    }
}
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/normalize/AucDeltaCalculator.java' <<'EOF_LINEAGE_FIX'
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
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/normalize/CanonicalIdResolver.java' <<'EOF_LINEAGE_FIX'
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
        if (index.hasUid(localId)) {
            return localId;
        }
        Set<String> uids = index.uidsForAlias(localId);
        if (uids.isEmpty()) {
            throw new AuditException(ExitCodes.VALIDATION, "UNKNOWN_RUN", "unknown run for id: " + localId);
        }
        if (uids.size() > 1) {
            throw new AuditException(ExitCodes.VALIDATION, "AMBIGUOUS_ALIAS",
                "ambiguous alias " + localId + " resolves to " + uids);
        }
        return uids.iterator().next();
    }
}
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/normalize/FeaturePathBuilder.java' <<'EOF_LINEAGE_FIX'
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
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/policy/AnnotationPolicy.java' <<'EOF_LINEAGE_FIX'
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
        List<Candidate> live = new ArrayList<>();
        for (Candidate c : candidates) {
            if (!"superseded".equals(c.status)) live.add(c);
        }
        if (live.isEmpty()) return "unspecified";
        boolean anyApproved = false;
        for (Candidate c : live) {
            if ("approved".equals(c.status)) { anyApproved = true; break; }
        }
        List<Candidate> pool = new ArrayList<>();
        for (Candidate c : live) {
            boolean isApproved = "approved".equals(c.status);
            if (isApproved == anyApproved) pool.add(c);
        }
        pool.sort(Comparator.comparing((Candidate c) -> c.date).thenComparing(c -> c.content));
        return pool.get(pool.size() - 1).content;
    }
}
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/report/DiscrepancyClassifier.java' <<'EOF_LINEAGE_FIX'
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
                out.representationDiffs.add(new Reconciliation.Diff("alias_spelling", r.runUid, null, aliases));
            }
        }
        for (EdgePlacement p : placements) {
            if (p.carriers.size() > 1) {
                out.representationDiffs.add(new Reconciliation.Diff("annotation_placement", null, p.edge, p.carriers));
            }
        }
    }
}
EOF_LINEAGE_FIX

cat > 'src/main/java/com/acme/lineage/util/AtomicOutput.java' <<'EOF_LINEAGE_FIX'
package com.acme.lineage.util;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class AtomicOutput {
    private AtomicOutput() {}

    // FIXED: build both payloads, stage both to temp files, then move both into
    // place. Neither final output appears unless both were written successfully.
    public static void commit(Path outDir, String dotName, String dot, String jsonName, String json) {
        try {
            Files.createDirectories(outDir);
            Path dotTmp = outDir.resolve(dotName + ".tmp");
            Path jsonTmp = outDir.resolve(jsonName + ".tmp");
            Files.writeString(dotTmp, dot);
            Files.writeString(jsonTmp, json);
            Files.move(dotTmp, outDir.resolve(dotName), StandardCopyOption.REPLACE_EXISTING);
            Files.move(jsonTmp, outDir.resolve(jsonName), StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            throw new AuditException(1, "IO_ERROR", "cannot write outputs: " + e.getMessage());
        }
    }
}
EOF_LINEAGE_FIX

./gradlew --offline --no-daemon clean test installDist

OUT="$(mktemp -d)"
OUT2="$(mktemp -d)"
/app/bin/lineage-audit \
    --left /app/worktrees/rc-blue \
    --right /app/worktrees/rc-green \
    --ledger /data/training-runs.csv \
    --dossier /data/model-review-dossier.md \
    --output-dir "${OUT}"
dot -Tcanon "${OUT}/lineage.dot" >/dev/null
jq . "${OUT}/discrepancies.json" >/dev/null

/app/bin/lineage-audit \
    --left /app/worktrees/rc-green \
    --right /app/worktrees/rc-blue \
    --ledger /data/training-runs.csv \
    --dossier /data/model-review-dossier.md \
    --output-dir "${OUT2}"
cmp "${OUT}/lineage.dot" "${OUT2}/lineage.dot"
cmp "${OUT}/discrepancies.json" "${OUT2}/discrepancies.json"

rm -rf "${OUT}" "${OUT2}"
echo "solve.sh: reconciliation build and smoke checks passed"
