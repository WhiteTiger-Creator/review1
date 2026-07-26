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
        if (is(DotLexer.Kind.LBRACK)) {
            next();
            while (!is(DotLexer.Kind.RBRACK)) {
                if (is(DotLexer.Kind.EOF)) throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_DOT", "unterminated attr list");
                String key = readId();
                expect(DotLexer.Kind.EQUALS);
                String value = readId();
                if (key.equals("label")) attrs.add(new DotGraph.Attr(key, value));
                if (is(DotLexer.Kind.COMMA)) next();
            }
            expect(DotLexer.Kind.RBRACK);
        }
        return attrs;
    }
}
