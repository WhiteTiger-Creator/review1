#!/bin/bash
set -euo pipefail

cd /app/environment

cat > flow/FlowKernel.java <<'EOF'
package terrain;

public final class FlowKernel {
    private FlowKernel() {}

    public record Cell(double water, double sediment) {}

    public static Cell advance(double height, double priorWater, double priorSediment,
                               double rainfall, int x, int y) {
        double slope = 0.0001 * ((x + 3 * y) % 11);
        double incoming = rainfall * (1.0 + slope) + priorWater * 0.00001;
        if (!Double.isFinite(incoming) || !Double.isFinite(priorSediment)) {
            return new Cell(0.0, priorSediment);
        }
        return new Cell(incoming, priorSediment);
    }

    public static double transfer(double amount, double edgeFactor) {
        if (!Double.isFinite(amount) || !Double.isFinite(edgeFactor)) {
            return 0.0;
        }
        return amount * edgeFactor;
    }

    public static double export(double water, int x, int y, int width, int height) {
        boolean border = x == 0 || y == 0 || x == width - 1 || y == height - 1;
        if (!border || water <= 0.0) {
            return 0.0;
        }
        return transfer(water, 0.000001);
    }
}
EOF

cat > flow/RainfallTable.java <<'EOF'
package terrain;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class RainfallTable {
    private final List<Double> values = new ArrayList<>();
    private final double fallback;

    private RainfallTable(double fallback) {
        this.fallback = fallback;
    }

    public static RainfallTable load(Path csv, double fallback) throws IOException {
        RainfallTable table = new RainfallTable(fallback);
        List<String> lines = Files.readAllLines(csv);
        for (int i = 1; i < lines.size(); i++) {
            String line = lines.get(i).trim();
            if (line.isEmpty()) {
                continue;
            }
            String[] parts = line.split(",");
            if (parts.length < 2) {
                continue;
            }
            table.values.add(Double.parseDouble(parts[1].trim()));
        }
        return table;
    }

    public double at(int step) {
        if (step < 0 || step >= values.size()) {
            return fallback;
        }
        return values.get(step);
    }

    public int size() {
        return values.size();
    }
}
EOF

cat > core/TileBuffer.java <<'EOF'
package terrain;

public final class TileBuffer {
    private final CellState[] slots;
    private int filled;
    private long peak;

    public TileBuffer(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity");
        }
        this.slots = new CellState[capacity];
        this.filled = 0;
        this.peak = 0;
    }

    public void beginTile() {
        for (int i = 0; i < filled; i++) {
            slots[i] = null;
        }
        filled = 0;
    }

    public void put(CellState state) {
        if (state == null) {
            throw new IllegalArgumentException("state");
        }
        if (filled >= slots.length) {
            throw new IllegalStateException("tile capacity exceeded");
        }
        slots[filled++] = state;
        if (filled > peak) {
            peak = filled;
        }
    }

    public void endTile() {
        if (filled > peak) {
            peak = filled;
        }
    }

    public long peakCells() {
        return peak;
    }

    public int capacity() {
        return slots.length;
    }

    public int residents() {
        return filled;
    }
}
EOF

cat > core/SedimentLedger.java <<'EOF'
package terrain;

public final class SedimentLedger {
    private final double initial;
    private double sediment;
    private int observations;
    private int commits;

    public SedimentLedger(double initial) {
        if (!Double.isFinite(initial)) {
            throw new IllegalArgumentException("initial");
        }
        this.initial = initial;
        this.sediment = initial;
        this.observations = 0;
        this.commits = 0;
    }

    public double value() {
        return sediment;
    }

    public double initialValue() {
        return initial;
    }

    public void observeCell(double carried) {
        if (!Double.isFinite(carried)) {
            throw new IllegalArgumentException("carried");
        }
        sediment = carried;
        observations += 1;
    }

    public void commitTile() {
        commits += 1;
    }

    public int observationCount() {
        return observations;
    }

    public int commitCount() {
        return commits;
    }

    public double error() {
        return Math.abs(sediment - initial);
    }
}
EOF

cat > core/TileCursor.java <<'EOF'
package terrain;

public final class TileCursor {
    private TileCursor() {}

    public static int tileCount(int width, int height, int tileWidth, int tileHeight) {
        return tilesX(width, tileWidth) * tilesY(height, tileHeight);
    }

    public static int tileCells(int tileWidth, int tileHeight) {
        return Math.multiplyExact(tileWidth, tileHeight);
    }

    public static int tilesX(int width, int tileWidth) {
        if (tileWidth <= 0) {
            throw new IllegalArgumentException("tileWidth");
        }
        return (width + tileWidth - 1) / tileWidth;
    }

    public static int tilesY(int height, int tileHeight) {
        if (tileHeight <= 0) {
            throw new IllegalArgumentException("tileHeight");
        }
        return (height + tileHeight - 1) / tileHeight;
    }
}
EOF

cat > reduce/ReductionLog.java <<'EOF'
package terrain;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

public final class ReductionLog {
    private ReductionLog() {}

    public static String append(int step, double terrain, double water,
                                double sediment, double edgeExport) {
        return String.format(Locale.ROOT, "%d|%.12f|%.12f|%.12f|%.12f;", step,
                terrain, water, sediment, edgeExport);
    }

    public static String digest(String text) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(64);
            for (byte value : bytes) {
                result.append(String.format(Locale.ROOT, "%02x", value & 255));
            }
            return result.toString();
        } catch (Exception ex) {
            throw new IllegalStateException("digest unavailable", ex);
        }
    }
}
EOF

cat > core/Main.java <<'EOF'
package terrain;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Properties;

public final class Main {
    private Main() {}

    public static void main(String[] args) throws Exception {
        execute(args.length > 0 && "--alternate".equals(args[0]));
    }

    static void execute(boolean alternate) throws Exception {
        Properties p = new Properties();
        Path profile = Path.of(alternate
                ? "/app/environment/config/alternate.properties"
                : "/app/environment/config/run.properties");
        try (var in = Files.newInputStream(profile)) {
            p.load(in);
        }
        int width = Integer.parseInt(p.getProperty("width"));
        int height = Integer.parseInt(p.getProperty("height"));
        int steps = Integer.parseInt(p.getProperty("steps"));
        int tileWidth = Integer.parseInt(p.getProperty("tile_width"));
        int tileHeight = Integer.parseInt(p.getProperty("tile_height"));
        long budget = Long.parseLong(p.getProperty("working_set_budget"));
        double fallbackRain = Double.parseDouble(p.getProperty("rainfall"));
        Path rainPath = Path.of(p.getProperty("rainfall_csv"));
        RainfallTable rains = RainfallTable.load(rainPath, fallbackRain);

        int tilesX = TileCursor.tilesX(width, tileWidth);
        int tilesY = TileCursor.tilesY(height, tileHeight);
        TileBuffer buffer = new TileBuffer(TileCursor.tileCells(tileWidth, tileHeight));
        SedimentLedger ledger = new SedimentLedger(1.0);
        List<String> records = new ArrayList<>();

        for (int step = 0; step < steps; step++) {
            double rainfall = rains.at(step);
            double terrain = 0.0;
            double water = 0.0;
            double edge = 0.0;
            double runningWater = 0.0;
            for (int ty = 0; ty < tilesY; ty++) {
                for (int tx = 0; tx < tilesX; tx++) {
                    buffer.beginTile();
                    int x0 = tx * tileWidth;
                    int y0 = ty * tileHeight;
                    int x1 = Math.min(width, x0 + tileWidth);
                    int y1 = Math.min(height, y0 + tileHeight);
                    for (int y = y0; y < y1; y++) {
                        for (int x = x0; x < x1; x++) {
                            double h = HeightField.value(x, y);
                            FlowKernel.Cell cell = FlowKernel.advance(
                                    h, runningWater, ledger.value(), rainfall, x, y);
                            ledger.observeCell(cell.sediment());
                            runningWater += cell.water();
                            terrain += h;
                            water += cell.water();
                            edge += FlowKernel.export(cell.water(), x, y, width, height);
                            buffer.put(new CellState(h, cell.water(), cell.sediment()));
                        }
                    }
                    ledger.commitTile();
                    buffer.endTile();
                }
            }
            records.add(ReductionLog.append(step, terrain, water, ledger.value(), edge));
        }

        writeReport(width, height, steps, budget, buffer.peakCells(),
                TileCursor.tileCount(width, height, tileWidth, tileHeight),
                ledger.initialValue(), ledger.value(), records, alternate);
    }

    private static void writeReport(int width, int height, int steps, long budget,
                                    long peak, int tiles, double initial,
                                    double finalSediment, List<String> records,
                                    boolean alternate) throws Exception {
        String digest = ReductionLog.digest(String.join("", records));
        StringBuilder out = new StringBuilder();
        out.append("{\"grid_width\":").append(width)
                .append(",\"grid_height\":").append(height)
                .append(",\"steps\":").append(steps)
                .append(",\"budget_cells\":").append(budget)
                .append(",\"peak_cells\":").append(peak)
                .append(",\"initial_sediment\":")
                .append(String.format(Locale.ROOT, "%.17g", initial))
                .append(",\"final_sediment\":")
                .append(String.format(Locale.ROOT, "%.17g", finalSediment))
                .append(",\"sediment_error\":")
                .append(String.format(Locale.ROOT, "%.17g",
                        Math.abs(finalSediment - initial)))
                .append(",\"tile_count\":").append(tiles)
                .append(",\"reduction_digest\":\"").append(digest).append("\"")
                .append(",\"profile\":\"")
                .append(alternate ? "alternate" : "primary").append("\"")
                .append(",\"runs\":[");
        for (int i = 0; i < records.size(); i++) {
            if (i > 0) {
                out.append(',');
            }
            String body = records.get(i);
            if (body.endsWith(";")) {
                body = body.substring(0, body.length() - 1);
            }
            String[] value = body.split("\\|", -1);
            out.append("{\"step\":").append(value[0])
                    .append(",\"terrain_sum\":").append(value[1])
                    .append(",\"water_sum\":").append(value[2])
                    .append(",\"sediment_sum\":").append(value[3])
                    .append(",\"edge_export\":").append(value[4]).append('}');
        }
        out.append("]}\n");
        Files.createDirectories(Path.of("/app/output"));
        Files.writeString(Path.of("/app/output/field_report.json"), out.toString());
    }
}
EOF

bash /app/environment/scripts/build_and_run.sh
