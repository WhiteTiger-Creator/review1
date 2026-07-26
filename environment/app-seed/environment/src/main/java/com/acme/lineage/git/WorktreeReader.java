package com.acme.lineage.git;

import com.acme.lineage.cli.ExitCodes;
import com.acme.lineage.dot.DotGraph;
import com.acme.lineage.dot.DotParser;
import com.acme.lineage.util.AuditException;
import java.io.IOException;
import java.io.Reader;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Properties;

public final class WorktreeReader {
    public final DotGraph graph;
    public final Properties props;

    private WorktreeReader(DotGraph graph, Properties props) {
        this.graph = graph;
        this.props = props;
    }

    public static WorktreeReader read(Path dir) {
        if (!Files.isDirectory(dir)) {
            throw new AuditException(ExitCodes.USAGE, "USAGE", "worktree not found: " + dir);
        }
        DotGraph merged = new DotGraph();
        Path lineage = dir.resolve("lineage");
        List<Path> shards = new ArrayList<>();
        try {
            if (Files.isDirectory(lineage)) {
                try (DirectoryStream<Path> ds = Files.newDirectoryStream(lineage, "*.dot")) {
                    for (Path p : ds) shards.add(p);
                }
            }
        } catch (IOException e) {
            throw new AuditException(ExitCodes.USAGE, "USAGE", "cannot read worktree: " + e.getMessage());
        }
        Collections.sort(shards);
        for (Path shard : shards) {
            String src;
            try {
                src = Files.readString(shard);
            } catch (IOException e) {
                throw new AuditException(ExitCodes.USAGE, "USAGE", "cannot read shard: " + shard);
            }
            DotGraph g = DotParser.parse(src);
            for (DotGraph.Node nid : g.nodes.values()) {
                merged.nodeFor(nid.id).attrs.addAll(nid.attrs);
            }
            merged.edges.addAll(g.edges);
        }
        Properties props = new Properties();
        Path pf = dir.resolve(".lineage-audit.properties");
        if (Files.isRegularFile(pf)) {
            try (Reader r = Files.newBufferedReader(pf)) {
                props.load(r);
            } catch (IOException ignored) {
            }
        }
        return new WorktreeReader(merged, props);
    }
}
