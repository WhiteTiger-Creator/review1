package glideclash.api;

import java.util.Objects;

public record ArenaEvent(
    long tick, int subframe, EventKind kind, String primaryId, String secondaryId
) {
    public ArenaEvent {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(primaryId, "primaryId");
        Objects.requireNonNull(secondaryId, "secondaryId");
    }
}
