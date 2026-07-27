import glideclash.api.Action;
import glideclash.api.Blueprint;
import glideclash.api.Engine;
import glideclash.api.Goal;
import glideclash.api.PaddleSeed;
import glideclash.api.PuckSeed;
import glideclash.api.Rules;
import glideclash.api.Side;
import glideclash.api.Snapshot;
import java.util.List;

public final class SmokeHarness {
    private SmokeHarness() {}

    public static void main(String[] args) {
        Blueprint bp = new Blueprint(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            List.of(new PuckSeed("puck", 100, 100, 4, 0, 5)),
            List.of(new PaddleSeed(
                "pad-a", 1, 40, 100, 8, 10, 0, 80, 20, 180
            )),
            List.of(),
            List.of(),
            List.of(
                new Goal("goal-l", Side.LEFT, 60, 140),
                new Goal("goal-r", Side.RIGHT, 60, 140)
            )
        );
        Engine engine = Engine.start(bp);
        Snapshot before = engine.snapshot();
        if (before.pucks().isEmpty()) {
            throw new IllegalStateException("missing puck");
        }
        try {
            before.pucks().add(before.pucks().get(0));
            throw new IllegalStateException("mutable pucks");
        } catch (UnsupportedOperationException expected) {
            // immutable
        }
        engine.submit(new glideclash.api.InputFrame(1, 0, 1, Action.EAST));
        engine.advanceTo(2);
        if (engine.headTick() != 2) {
            throw new IllegalStateException("head");
        }
        Snapshot after = engine.snapshot();
        if (after.pucks().get(0).x() == before.pucks().get(0).x()
            && after.pucks().get(0).xRemainder() == before.pucks().get(0).xRemainder()) {
            throw new IllegalStateException("puck did not move");
        }
    }
}
