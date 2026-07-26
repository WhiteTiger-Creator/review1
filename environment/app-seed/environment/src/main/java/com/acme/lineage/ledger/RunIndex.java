package com.acme.lineage.ledger;

import com.acme.lineage.model.RunRecord;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public final class RunIndex {
    private final Map<String, RunRecord> byUid = new LinkedHashMap<>();
    private final Map<String, Set<String>> aliasToUids = new HashMap<>();

    public void add(RunRecord r) {
        byUid.put(r.runUid, r);
        register(r.releaseAlias, r.runUid);
        register(r.legacyAlias, r.runUid);
    }

    private void register(String alias, String uid) {
        if (alias == null || alias.isEmpty()) return;
        aliasToUids.computeIfAbsent(alias, k -> new TreeSet<>()).add(uid);
    }

    public RunRecord byUid(String uid) { return byUid.get(uid); }
    public boolean hasUid(String uid) { return byUid.containsKey(uid); }
    public Set<String> uidsForAlias(String alias) {
        return aliasToUids.getOrDefault(alias, Collections.emptySet());
    }
    public Collection<RunRecord> all() { return byUid.values(); }
}
