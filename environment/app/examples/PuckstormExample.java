import glideclash.api.Action;
import glideclash.api.Blueprint;
import glideclash.api.Engine;
import glideclash.api.GlideFrame;
import glideclash.api.Goal;
import glideclash.api.InputFrame;
import glideclash.api.PaddleSeed;
import glideclash.api.PuckSeed;
import glideclash.api.Rules;
import glideclash.api.Side;
import java.util.List;

public final class PuckstormExample {
    private PuckstormExample() {}

    public static void main(String[] args) {
        Blueprint bp = new Blueprint(
            new Rules(400, 240, 8, 16, 1, 40, 20),
            List.of(new PuckSeed("alpha", 200, 120, 12, 4, 6)),
            List.of(
                new PaddleSeed("left-pad", 1, 60, 120, 10, 16, 0, 120, 40, 200),
                new PaddleSeed("right-pad", 2, 340, 120, 10, 16, 280, 400, 40, 200)
            ),
            List.of(),
            List.of(),
            List.of(
                new Goal("west", Side.LEFT, 80, 160),
                new Goal("east", Side.RIGHT, 80, 160)
            )
        );
        Engine engine = Engine.start(bp);
        engine.submit(new InputFrame(1, 0, 1, Action.EAST));
        engine.submit(new InputFrame(2, 0, 1, Action.WEST));
        List<GlideFrame> frames = engine.advanceTo(3);
        System.out.println("frames=" + frames.size() + " head=" + engine.headTick());
    }
}
