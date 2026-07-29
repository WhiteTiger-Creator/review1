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
            table.values.add(Double.parseDouble(parts[1].trim()));
        }
        return table;
    }

    public double at(int step) {
        if (values.isEmpty()) {
            return fallback;
        }
        int index = values.size() - 1 - step;
        if (index < 0 || index >= values.size()) {
            return fallback;
        }
        return values.get(index);
    }

    public int size() {
        return values.size();
    }
}
