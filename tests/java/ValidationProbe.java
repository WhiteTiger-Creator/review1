import glideclash.api.Action;
import glideclash.api.Axis;
import glideclash.api.Blueprint;
import glideclash.api.BlueprintException;
import glideclash.api.Bumper;
import glideclash.api.Engine;
import glideclash.api.Gate;
import glideclash.api.Goal;
import glideclash.api.InputFrame;
import glideclash.api.InputReceipt;
import glideclash.api.PaddleSeed;
import glideclash.api.PuckSeed;
import glideclash.api.Rules;
import glideclash.api.Side;
import java.util.ArrayList;
import java.util.List;

public final class ValidationProbe {
    private ValidationProbe() {}

    public static void main(String[] args) {
        if (args.length < 1) {
            throw new IllegalArgumentException("scenario");
        }
        switch (args[0]) {
            case "precedence" -> precedence();
            case "mid-codes" -> midCodes();
            case "invalid-input" -> invalidInput();
            default -> throw new IllegalArgumentException(args[0]);
        }
    }

    static void precedence() {
        // Multiple errors: rules + duplicate-id + null-member — rules should win
        try {
            Blueprint bp = new Blueprint(
                new Rules(50, 200, 4, 8, 0, 20, 10), // bad width -> rules
                List.of(new PuckSeed("dup", 80, 100, 0, 0, 5), new PuckSeed("dup", 120, 100, 0, 0, 5)),
                List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
                List.of(),
                List.of(),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("ok=true");
        } catch (BlueprintException ex) {
            System.out.println("code=" + ex.code());
            System.out.println("id=" + ex.id());
        }

        // duplicate-id vs player: duplicate should win (earlier)
        try {
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
                List.of(
                    new PaddleSeed("a-pad", 1, 40, 100, 8, 10, 0, 80, 20, 180),
                    new PaddleSeed("a-pad", 1, 60, 100, 8, 10, 0, 80, 20, 180)
                ),
                List.of(),
                List.of(),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("dup.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("dup.code=" + ex.code());
            System.out.println("dup.id=" + ex.id());
        }

        // Two overlap offenders: pick lexical smallest id
        try {
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
                List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
                List.of(new Bumper("zb", 100, 100, 8, 0), new Bumper("ya", 100, 100, 8, 0)),
                List.of(),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("ov.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("ov.code=" + ex.code());
            System.out.println("ov.id=" + ex.id());
        }

        // null-member last
        try {
            List<PuckSeed> pucks = new ArrayList<>();
            pucks.add(new PuckSeed("p", 100, 100, 0, 0, 5));
            pucks.add(null);
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                pucks,
                List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
                List.of(),
                List.of(),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("nm.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("nm.code=" + ex.code());
            System.out.println("nm.id=" + ex.id());
        } catch (NullPointerException ex) {
            System.out.println("nm.npe=true");
        }
    }

    static void midCodes() {
        // player: out-of-range player id
        try {
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
                List.of(new PaddleSeed("pad", 9, 40, 100, 8, 10, 0, 80, 20, 180)),
                List.of(),
                List.of(),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("player.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("player.code=" + ex.code());
            System.out.println("player.id=" + ex.id());
        }

        // bounds: puck circle not wholly inside rink
        try {
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                List.of(new PuckSeed("out", 3, 100, 0, 0, 5)),
                List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
                List.of(),
                List.of(),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("bounds.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("bounds.code=" + ex.code());
            System.out.println("bounds.id=" + ex.id());
        }

        // home: paddle circle not contained by home box
        try {
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
                List.of(new PaddleSeed("pad", 1, 10, 100, 8, 10, 20, 80, 20, 180)),
                List.of(),
                List.of(),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("home.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("home.code=" + ex.code());
            System.out.println("home.id=" + ex.id());
        }

        // goal: two LEFT mouths, zero RIGHT
        try {
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
                List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
                List.of(),
                List.of(),
                List.of(new Goal("aa", Side.LEFT, 40, 160), new Goal("bb", Side.LEFT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("goal.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("goal.code=" + ex.code());
            System.out.println("goal.id=" + ex.id());
        }

        // gate: blockedSign neither -1 nor 1
        try {
            Blueprint bp = new Blueprint(
                new Rules(200, 200, 4, 8, 0, 20, 10),
                List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
                List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
                List.of(),
                List.of(new Gate("gx", Axis.X, 100, 40, 160, 0)),
                List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
            );
            Engine.start(bp);
            System.out.println("gate.ok=true");
        } catch (BlueprintException ex) {
            System.out.println("gate.code=" + ex.code());
            System.out.println("gate.id=" + ex.id());
        }
    }

    static void invalidInput() {
        Blueprint bp = new Blueprint(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of(),
            List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
        );
        Engine eng = Engine.start(bp);
        InputReceipt a = eng.submit(new InputFrame(9, 0, 1, Action.EAST));
        InputReceipt b = eng.submit(new InputFrame(1, -1, 1, Action.EAST));
        System.out.println("unknown=" + a.status());
        System.out.println("invalid=" + b.status());
        System.out.println("head=" + eng.headTick());
    }
}
