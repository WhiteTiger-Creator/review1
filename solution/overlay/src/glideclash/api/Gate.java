package glideclash.api;

public record Gate(
    String id, Axis axis, int coordinate, int low, int high, int blockedSign
) {
    public Gate {
        if (id == null) {
            throw new NullPointerException("id");
        }
        if (axis == null) {
            throw new NullPointerException("axis");
        }
    }
}
