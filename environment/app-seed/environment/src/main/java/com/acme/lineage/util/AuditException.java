package com.acme.lineage.util;

public class AuditException extends RuntimeException {
    public final int exitCode;
    public final String token;

    public AuditException(int exitCode, String token, String message) {
        super(message);
        this.exitCode = exitCode;
        this.token = token;
    }
}
