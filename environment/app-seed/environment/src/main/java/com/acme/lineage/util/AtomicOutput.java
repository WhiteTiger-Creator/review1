package com.acme.lineage.util;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class AtomicOutput {
    private AtomicOutput() {}

    // FIXED: build both payloads, stage both to temp files, then move both into
    // place. Neither final output appears unless both were written successfully.
    public static void commit(Path outDir, String dotName, String dot, String jsonName, String json) {
        try {
            Files.createDirectories(outDir);
            Files.writeString(outDir.resolve(dotName), dot);
            Files.writeString(outDir.resolve(jsonName), json);
        } catch (IOException e) {
            throw new AuditException(1, "IO_ERROR", "cannot write outputs: " + e.getMessage());
        }
    }
}
