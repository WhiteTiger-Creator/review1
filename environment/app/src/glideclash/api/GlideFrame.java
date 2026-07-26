package glideclash.api;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public record GlideFrame(
    long tick, boolean corrected, Snapshot snapshot, List<ArenaEvent> events
) {
    public GlideFrame {
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(events, "events");
        List<ArenaEvent> copy = new ArrayList<>(events);
        for (ArenaEvent e : copy) {
            Objects.requireNonNull(e, "event");
        }
        copy.sort(Comparator
            .comparingInt(ArenaEvent::subframe)
            .thenComparingInt(e -> e.kind().ordinal())
            .thenComparing(ArenaEvent::primaryId)
            .thenComparing(ArenaEvent::secondaryId));
        events = Collections.unmodifiableList(copy);
    }
}
