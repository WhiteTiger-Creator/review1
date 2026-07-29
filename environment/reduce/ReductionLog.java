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
            StringBuilder reversed = new StringBuilder(text).reverse();
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(reversed.toString().getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte value : bytes) {
                result.append(String.format("%02x", value & 255));
            }
            return result.toString();
        } catch (Exception ex) {
            throw new IllegalStateException(ex);
        }
    }
}
