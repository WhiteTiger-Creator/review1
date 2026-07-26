package com.acme.lineage.config;

import java.util.Map;

public final class AuditConfig {
    private final Map<String, String> values;

    public AuditConfig(Map<String, String> values) { this.values = values; }

    public String get(String key, String def) {
        return values.getOrDefault(key, def);
    }
}
