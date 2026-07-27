package glideclash.api;

public record Goal(String id, Side side, int low, int high) {
    public Goal {
        if (id == null) {
            throw new NullPointerException("id");
        }
        if (side == null) {
            throw new NullPointerException("side");
        }
    }
}
