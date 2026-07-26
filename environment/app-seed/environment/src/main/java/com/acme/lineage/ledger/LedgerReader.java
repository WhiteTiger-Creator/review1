package com.acme.lineage.ledger;

import com.acme.lineage.cli.ExitCodes;
import com.acme.lineage.model.RunRecord;
import com.acme.lineage.util.AuditException;
import com.acme.lineage.util.Csv;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class LedgerReader {
    private LedgerReader() {}

    public static RunIndex read(Path csv) {
        List<String> lines;
        try {
            lines = Files.readAllLines(csv);
        } catch (IOException e) {
            throw new AuditException(ExitCodes.USAGE, "USAGE", "cannot read ledger: " + e.getMessage());
        }
        if (lines.isEmpty()) {
            throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_LEDGER", "empty ledger");
        }
        RunIndex idx = new RunIndex();
        for (int i = 1; i < lines.size(); i++) {
            String line = lines.get(i);
            if (line.isBlank()) continue;
            List<String> c = Csv.split(line);
            if (c.size() < 9) {
                throw new AuditException(ExitCodes.VALIDATION, "MALFORMED_LEDGER", "short ledger row " + i);
            }
            RunRecord r = new RunRecord(
                c.get(0), c.get(1), c.get(2), c.get(4), c.get(5), c.get(6), c.get(7), c.get(8));
            idx.add(r);
        }
        return idx;
    }
}
