package com.acme.lineage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.acme.lineage.dot.DotGraph;
import com.acme.lineage.dot.DotLexer;
import com.acme.lineage.dot.DotParser;
import java.util.List;
import org.junit.jupiter.api.Test;

public class BasicShapeTest {
    @Test
    void lexerTokenizesEdge() {
        List<DotLexer.Token> t = DotLexer.lex("digraph g { \"a\" -> \"b\" [label=\"x\"]; }");
        assertTrue(t.size() > 5);
    }

    @Test
    void parserReadsNodeAndEdge() {
        DotGraph g = DotParser.parse(
            "digraph g { \"a\"; \"a\" -> \"b\" [label=\"proposal|2024-01-01|warmstart\"]; }");
        assertTrue(g.nodes.containsKey("a"));
        assertEquals(1, g.edges.size());
    }
}
