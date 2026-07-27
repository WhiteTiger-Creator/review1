package glideclash.api;

import java.util.Objects;

public record PlayerAction(int player, Action action) {
    public PlayerAction {
        Objects.requireNonNull(action, "action");
    }
}
