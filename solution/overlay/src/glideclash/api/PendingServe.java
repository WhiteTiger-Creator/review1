package glideclash.api;

import java.util.Objects;

public record PendingServe(String puckId, Side exitedSide) {
    public PendingServe {
        Objects.requireNonNull(puckId, "puckId");
        Objects.requireNonNull(exitedSide, "exitedSide");
    }
}
