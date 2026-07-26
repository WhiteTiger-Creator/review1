package com.acme.lineage.cli;

public final class ExitCodes {
    public static final int OK = 0;
    public static final int USAGE = 1;
    public static final int VALIDATION = 2; // ambiguous alias, unknown run, malformed dot
    public static final int CONFLICT = 3;   // conflicting parentage / metrics
    private ExitCodes() {}
}
