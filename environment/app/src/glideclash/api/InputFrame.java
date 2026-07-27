package glideclash.api;

import java.util.Objects;

public record InputFrame(int player, long tick, long sequence, Action action) {
    public InputFrame {
        Objects.requireNonNull(action, "action");
    }
}
