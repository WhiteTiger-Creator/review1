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
            if (branch.containsKey(k)) {
                resolved.put(k, branch.get(k));
            } else if (cli.containsKey(k)) {
                resolved.put(k, cli.get(k));
            } else {
                resolved.put(k, defaults.getProperty(k));
            }
        }
        return new AuditConfig(resolved);
    }
}
