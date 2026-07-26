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
            Path dotTmp = outDir.resolve(dotName + ".tmp");
            Path jsonTmp = outDir.resolve(jsonName + ".tmp");
            Files.writeString(dotTmp, dot);
            Files.writeString(jsonTmp, json);
            Files.move(dotTmp, outDir.resolve(dotName), StandardCopyOption.REPLACE_EXISTING);
            Files.move(jsonTmp, outDir.resolve(jsonName), StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            throw new AuditException(1, "IO_ERROR", "cannot write outputs: " + e.getMessage());
        }
    }
}
