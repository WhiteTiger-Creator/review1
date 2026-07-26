package com.acme.lineage.cli;

import com.acme.lineage.config.AuditConfig;
import com.acme.lineage.config.ConfigLoader;
import com.acme.lineage.dot.CanonicalDotWriter;
import com.acme.lineage.git.WorktreeReader;
import com.acme.lineage.ledger.LedgerReader;
import com.acme.lineage.ledger.RunIndex;
import com.acme.lineage.model.Reconciliation;
import com.acme.lineage.normalize.LineageNormalizer;
import com.acme.lineage.report.JsonReportWriter;
import com.acme.lineage.util.AtomicOutput;
import com.acme.lineage.util.AuditException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

public final class AuditMain {
    private static final String VERSION = "lineage-audit 1.4.2";
    private static final String USAGE =
        "usage: lineage-audit --left DIR --right DIR --ledger CSV --dossier MD "
        + "--output-dir DIR [--set key=value]\n";

    public static void main(String[] args) {
        int code = run(args);
        if (code != 0) System.exit(code);
    }

    static int run(String[] args) {
        Map<String, String> opt = new HashMap<>();
        Map<String, String> sets = new LinkedHashMap<>();
        for (int i = 0; i < args.length; i++) {
            String a = args[i];
            switch (a) {
                case "--help":
                case "-h":
                    System.out.print(USAGE);
                    return ExitCodes.OK;
                case "--version":
                    System.out.println(VERSION);
                    return ExitCodes.OK;
                case "--left":
                case "--right":
                case "--ledger":
                case "--dossier":
                case "--output-dir":
                    if (i + 1 >= args.length) { System.err.print(USAGE); return ExitCodes.USAGE; }
                    opt.put(a.substring(2), args[++i]);
                    break;
                case "--set":
                    if (i + 1 >= args.length) { System.err.print(USAGE); return ExitCodes.USAGE; }
                    String kv = args[++i];
                    int eq = kv.indexOf('=');
                    if (eq < 0) { System.err.print(USAGE); return ExitCodes.USAGE; }
                    sets.put(kv.substring(0, eq), kv.substring(eq + 1));
                    break;
                default:
                    System.err.println("lineage-audit: unknown option: " + a);
                    System.err.print(USAGE);
                    return ExitCodes.USAGE;
            }
        }
        for (String req : new String[]{"left", "right", "ledger", "dossier", "output-dir"}) {
            if (!opt.containsKey(req)) {
                System.err.println("lineage-audit: missing required --" + req);
                System.err.print(USAGE);
                return ExitCodes.USAGE;
            }
        }
        Path ledger = Path.of(opt.get("ledger"));
        Path dossier = Path.of(opt.get("dossier"));
        Path leftDir = Path.of(opt.get("left"));
        Path rightDir = Path.of(opt.get("right"));
        Path outDir = Path.of(opt.get("output-dir"));
        if (!Files.isRegularFile(ledger)) {
            System.err.println("lineage-audit: ledger not found: " + ledger);
            return ExitCodes.USAGE;
        }
        if (!Files.isRegularFile(dossier)) {
            System.err.println("lineage-audit: dossier not found: " + dossier);
            return ExitCodes.USAGE;
        }
        try {
            RunIndex index = LedgerReader.read(ledger);
            WorktreeReader left = WorktreeReader.read(leftDir);
            WorktreeReader right = WorktreeReader.read(rightDir);
            Properties defaults = loadDefaults();
            AuditConfig config = ConfigLoader.load(defaults, left.props, right.props, sets);
            boolean acceptLegacy = !"strict".equals(config.get("annotation.legacy_attrs", "accept"));
            LineageNormalizer normalizer = new LineageNormalizer(index, acceptLegacy);
            Reconciliation r = normalizer.normalize(left, right);
            String dot = CanonicalDotWriter.write(r);
            String json = JsonReportWriter.write(r);
            AtomicOutput.commit(outDir, "lineage.dot", dot, "discrepancies.json", json);
            System.out.println("lineage-audit: reconciled " + r.nodes.size() + " nodes, " + r.edges.size() + " edges");
            return ExitCodes.OK;
        } catch (AuditException e) {
            System.err.println("lineage-audit: " + e.token + ": " + e.getMessage());
            return e.exitCode;
        }
    }

    private static Properties loadDefaults() {
        Properties p = new Properties();
        Path[] candidates = {
            Path.of("config/defaults.properties"),
            Path.of("/app/environment/config/defaults.properties"),
        };
        for (Path c : candidates) {
            if (Files.isRegularFile(c)) {
                try (Reader r = Files.newBufferedReader(c)) {
                    p.load(r);
                } catch (Exception ignored) {
                }
                break;
            }
        }
        if (p.isEmpty()) {
            p.setProperty("annotation.legacy_attrs", "accept");
            p.setProperty("alias.namespace", "both");
        }
        return p;
    }
}
