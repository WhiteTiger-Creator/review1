package com.acme.lineage.dot;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class DotGraph {
    public static final class Attr {
        public final String key;
        public final String value;
        public Attr(String key, String value) { this.key = key; this.value = value; }
    }

    public static final class Node {
        public final String id;
        public final List<Attr> attrs = new ArrayList<>();
        public Node(String id) { this.id = id; }
    }

    public static final class Edge {
        public final String src;
        public final String dst;
        public final List<Attr> attrs = new ArrayList<>();
        public Edge(String src, String dst) { this.src = src; this.dst = dst; }
    }

    public final Map<String, Node> nodes = new LinkedHashMap<>();
    public final List<Edge> edges = new ArrayList<>();

    public Node nodeFor(String id) {
        return nodes.computeIfAbsent(id, Node::new);
    }
}
