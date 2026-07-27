package glideclash.internal;

import glideclash.api.Action;
import glideclash.api.BodyView;
import glideclash.api.PendingServe;
import glideclash.api.PlayerAction;
import glideclash.api.Snapshot;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class ImmutableViews {
    private ImmutableViews() {}

    public static Snapshot snapshot(EngineState state) {
        List<BodyView> pucks = new ArrayList<>();
        for (String id : state.puckIds) {
            MutableBody b = state.puckById.get(id);
            if (b.active) {
                pucks.add(new BodyView(b.id, b.x, b.y, b.vx, b.vy, b.xRemainder, b.yRemainder));
            }
        }
        List<BodyView> pads = new ArrayList<>();
        for (MutableBody b : state.paddles) {
            pads.add(new BodyView(b.id, b.x, b.y, b.vx, b.vy, b.xRemainder, b.yRemainder));
        }
        List<PendingServe> serves = new ArrayList<>(state.pendingServes);
        List<PlayerAction> actions = new ArrayList<>();
        for (Map.Entry<Integer, Action> e : state.publishedActions.entrySet()) {
            actions.add(new PlayerAction(e.getKey(), e.getValue()));
        }
        return new Snapshot(
            state.headTick, state.leftScore, state.rightScore,
            pucks, pads, serves, actions
        );
    }
}
