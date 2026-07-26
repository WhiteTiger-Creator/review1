package glideclash.api;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public record Snapshot(
    long headTick, int leftScore, int rightScore,
    List<BodyView> pucks, List<BodyView> paddles,
    List<PendingServe> pendingServes, List<PlayerAction> actions
) {
    public Snapshot {
        Objects.requireNonNull(pucks, "pucks");
        Objects.requireNonNull(paddles, "paddles");
        Objects.requireNonNull(pendingServes, "pendingServes");
        Objects.requireNonNull(actions, "actions");
        pucks = freezeBodies(pucks);
        paddles = freezeBodies(paddles);
        pendingServes = freezeServes(pendingServes);
        actions = freezeActions(actions);
    }

    private static List<BodyView> freezeBodies(List<BodyView> in) {
        List<BodyView> copy = new ArrayList<>(in);
        for (BodyView b : copy) {
            Objects.requireNonNull(b, "body");
        }
        copy.sort(Comparator.comparing(BodyView::id));
        return Collections.unmodifiableList(copy);
    }

    private static List<PendingServe> freezeServes(List<PendingServe> in) {
        List<PendingServe> copy = new ArrayList<>(in);
        for (PendingServe s : copy) {
            Objects.requireNonNull(s, "serve");
        }
        copy.sort(Comparator.comparing(PendingServe::puckId));
        return Collections.unmodifiableList(copy);
    }

    private static List<PlayerAction> freezeActions(List<PlayerAction> in) {
        List<PlayerAction> copy = new ArrayList<>(in);
        for (PlayerAction a : copy) {
            Objects.requireNonNull(a, "action");
        }
        copy.sort(Comparator.comparingInt(PlayerAction::player));
        return Collections.unmodifiableList(copy);
    }
}
