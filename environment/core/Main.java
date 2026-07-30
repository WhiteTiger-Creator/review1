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
            records.add(0, ReductionLog.append(step, terrain, water, ledger.value(), edge));
        }

        long peak = Math.max(buffer.peakCells(), Domain.cells(width, height));
        int tiles = TileCursor.tileCount(width, height, tileWidth, tileHeight);
        writeReport(width, height, steps, budget, peak, tiles, 1.0, ledger.value(),
                records, alternate);
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
            String[] value = records.get(i).split("\\|", -1);
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
