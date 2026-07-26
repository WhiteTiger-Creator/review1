package glideclash.api;

import java.util.Objects;

public record BodyView(
    String id, int x, int y, int vx, int vy, int xRemainder, int yRemainder
) {
    public BodyView {
        Objects.requireNonNull(id, "id");
    }
}
