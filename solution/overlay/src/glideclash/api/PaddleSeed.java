package glideclash.api;

public record PaddleSeed(
    String id, int player, int x, int y, int radius, int speed,
    int homeMinX, int homeMaxX, int homeMinY, int homeMaxY
) {
    public PaddleSeed {
        if (id == null) {
            throw new NullPointerException("id");
        }
    }
}
