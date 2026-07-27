package glideclash.api;

public record Bumper(String id, int x, int y, int radius, int kick) {
    public Bumper {
        if (id == null) {
            throw new NullPointerException("id");
        }
    }
}
