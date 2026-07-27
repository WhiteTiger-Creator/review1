package glideclash.api;

public record PuckSeed(
    String id, int x, int y, int vx, int vy, int radius
) {
    public PuckSeed {
        if (id == null) {
            throw new NullPointerException("id");
        }
    }
}
