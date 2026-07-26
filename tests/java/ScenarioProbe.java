import glideclash.api.Action;
import glideclash.api.ArenaEvent;
import glideclash.api.Axis;
import glideclash.api.Blueprint;
import glideclash.api.BlueprintException;
import glideclash.api.BodyView;
import glideclash.api.Bumper;
import glideclash.api.Engine;
import glideclash.api.Gate;
import glideclash.api.GlideFrame;
import glideclash.api.Goal;
import glideclash.api.InputFrame;
import glideclash.api.InputReceipt;
import glideclash.api.PaddleSeed;
import glideclash.api.PendingServe;
import glideclash.api.PhysicsException;
import glideclash.api.PlayerAction;
import glideclash.api.PuckSeed;
import glideclash.api.Rules;
import glideclash.api.Side;
import glideclash.api.Snapshot;
import java.util.ArrayList;
import java.util.List;

public final class ScenarioProbe {
    private ScenarioProbe() {}

    public static void main(String[] args) {
        if (args.length < 1) {
            throw new IllegalArgumentException("scenario");
        }
        switch (args[0]) {
            case "pristine" -> pristine();
            case "floor-div" -> floorDiv();
            case "predict" -> predict();
            case "future-auth" -> futureAuth();
            case "wall" -> wall();
            case "gate" -> gate();
            case "goal" -> goal();
            case "respawn" -> respawn();
            case "bumper" -> bumper();
            case "paddle-hit" -> paddleHit();
            case "paddle-soft" -> paddleSoft();
            case "bumper-decay" -> bumperDecay();
            case "puck-swap" -> puckSwap();
            case "coincident" -> coincident();
            case "chain" -> chain();
            case "impact-limit" -> impactLimit();
            case "ricochet-cap" -> ricochetCap();
            case "home-clamp" -> homeClamp();
            case "friction" -> friction();
            case "chunked" -> chunked();
            case "permute" -> permute();
            case "mutate" -> mutate();
            default -> throw new IllegalArgumentException(args[0]);
        }
    }

    static Blueprint base(
        Rules rules,
        List<PuckSeed> pucks,
        List<PaddleSeed> paddles,
        List<Bumper> bumpers,
        List<Gate> gates
    ) {
        return new Blueprint(
            rules, pucks, paddles, bumpers, gates,
            List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
        );
    }

    static void printSnap(String tag, Snapshot s) {
        System.out.println(tag + ".head=" + s.headTick());
        System.out.println(tag + ".scores=" + s.leftScore() + "," + s.rightScore());
        for (BodyView b : s.pucks()) {
            System.out.println(tag + ".puck." + b.id() + "=" + b.x() + "," + b.y() + ","
                + b.vx() + "," + b.vy() + "," + b.xRemainder() + "," + b.yRemainder());
        }
        for (BodyView b : s.paddles()) {
            System.out.println(tag + ".pad." + b.id() + "=" + b.x() + "," + b.y() + ","
                + b.vx() + "," + b.vy() + "," + b.xRemainder() + "," + b.yRemainder());
        }
        for (PendingServe p : s.pendingServes()) {
            System.out.println(tag + ".serve." + p.puckId() + "=" + p.exitedSide());
        }
        for (PlayerAction a : s.actions()) {
            System.out.println(tag + ".act." + a.player() + "=" + a.action());
        }
    }

    static void printEvents(String tag, List<ArenaEvent> events) {
        for (ArenaEvent e : events) {
            System.out.println(tag + ".ev=" + e.tick() + "," + e.subframe() + ","
                + e.kind() + "," + e.primaryId() + "," + e.secondaryId());
        }
    }

    static void pristine() {
        List<PuckSeed> pucks = new ArrayList<>();
        pucks.add(new PuckSeed("b-puck", 120, 100, 0, 0, 5));
        pucks.add(new PuckSeed("a-puck", 80, 100, 0, 0, 5));
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            pucks,
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        Snapshot s = eng.snapshot();
        System.out.println("puck0=" + s.pucks().get(0).id());
        System.out.println("puck1=" + s.pucks().get(1).id());
        System.out.println("immutable=" + !(s.pucks() instanceof ArrayList));
        try {
            s.pucks().clear();
            System.out.println("mutated=true");
        } catch (UnsupportedOperationException ex) {
            System.out.println("mutated=false");
        }
        printSnap("s0", s);
    }

    static void floorDiv() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            List.of(new PuckSeed("p", 100, 100, -5, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.advanceTo(1);
        printSnap("t1", eng.snapshot());
    }

    static void predict() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        eng.advanceTo(3);
        printSnap("t3", eng.snapshot());
    }

    static void futureAuth() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        eng.submit(new InputFrame(1, 2, 1, Action.WEST));
        List<GlideFrame> frames = eng.advanceTo(3);
        for (GlideFrame f : frames) {
            System.out.println("frame." + f.tick() + ".act="
                + f.snapshot().actions().get(0).action());
            BodyView pad = f.snapshot().paddles().get(0);
            System.out.println("frame." + f.tick() + ".padx=" + pad.x());
        }
        printSnap("t3", eng.snapshot());
    }

    static void wall() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 20, 20, -40, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 100, 100, 8, 10, 60, 140, 60, 140)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("t0", frames.get(0).events());
        printSnap("t1", eng.snapshot());
    }

    static void gate() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 80, 100, 40, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(),
            List.of(new Gate("g1", Axis.X, 100, 50, 150, 1))
        );
        Engine eng = Engine.start(bp);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("block", frames.get(0).events());
        printSnap("block", eng.snapshot());

        Blueprint bp2 = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 120, 100, -40, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(),
            List.of(new Gate("g1", Axis.X, 100, 50, 150, 1))
        );
        Engine eng2 = Engine.start(bp2);
        List<GlideFrame> frames2 = eng2.advanceTo(1);
        printEvents("pass", frames2.get(0).events());
        printSnap("pass", eng2.snapshot());
    }

    static void goal() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 12, 100, -40, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 100, 40, 8, 10, 60, 140, 0, 80)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("g", frames.get(0).events());
        System.out.println("hasWall=" + frames.get(0).events().stream()
            .anyMatch(e -> e.kind().name().equals("WALL")));
        printSnap("t1", eng.snapshot());
    }

    static void respawn() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 12, 100, -40, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 100, 40, 8, 10, 60, 140, 0, 80)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.advanceTo(1);
        printSnap("afterGoal", eng.snapshot());
        eng.advanceTo(2);
        printSnap("afterServe", eng.snapshot());
    }

    static void bumper() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 70, 100, 20, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(new Bumper("bum", 100, 100, 10, 5)),
            List.of()
        );
        Engine eng = Engine.start(bp);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("b", frames.get(0).events());
        printSnap("t1", eng.snapshot());
    }

    static void paddleHit() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 70, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 20, 0, 90, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("h", frames.get(0).events());
        printSnap("t1", eng.snapshot());
    }

    static void paddleSoft() {
        // Tick 0 authoritative EAST establishes lastEffective; tick 1 is predicted EAST (no submit).
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 85, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 20, 0, 90, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        eng.advanceTo(1);
        List<GlideFrame> frames = eng.advanceTo(2);
        printEvents("s", frames.get(0).events());
        printSnap("t2", eng.snapshot());
    }

    static void bumperDecay() {
        // Hit br then bl in one tick: first response uses kick/1, second uses kick/2.
        Blueprint bp = base(
            new Rules(200, 200, 8, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 110, 100, 25, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(
                new Bumper("bl", 80, 100, 12, 8),
                new Bumper("br", 130, 100, 12, 8)
            ),
            List.of()
        );
        Engine eng = Engine.start(bp);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("d", frames.get(0).events());
        printSnap("t1", eng.snapshot());
    }

    static void puckSwap() {
        Blueprint bp = base(
            new Rules(300, 200, 4, 8, 0, 40, 10),
            List.of(
                new PuckSeed("a", 100, 100, 20, 3, 5),
                new PuckSeed("b", 130, 100, -10, 7, 5)
            ),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("s", frames.get(0).events());
        printSnap("t1", eng.snapshot());
    }

    static void coincident() {
        Blueprint bp = base(
            new Rules(300, 200, 2, 8, 0, 40, 10),
            List.of(
                new PuckSeed("a", 150, 100, 0, 0, 8),
                new PuckSeed("b", 150, 100, 0, 0, 8)
            ),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(),
            List.of()
        );
        // Overlap at start is invalid — place almost coincident via movement instead
        Blueprint bp2 = base(
            new Rules(300, 200, 2, 8, 0, 40, 10),
            List.of(
                new PuckSeed("a", 140, 100, 20, 0, 8),
                new PuckSeed("b", 160, 100, -20, 0, 8)
            ),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp2);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("c", frames.get(0).events());
        printSnap("t1", eng.snapshot());
    }

    static void chain() {
        Blueprint bp = base(
            new Rules(400, 200, 2, 8, 0, 50, 10),
            List.of(
                new PuckSeed("a", 100, 100, 30, 0, 8),
                new PuckSeed("b", 120, 100, 0, 0, 8),
                new PuckSeed("c", 140, 100, 0, 0, 8)
            ),
            List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        List<GlideFrame> frames = eng.advanceTo(1);
        printEvents("ch", frames.get(0).events());
        printSnap("t1", eng.snapshot());
    }

    static void impactLimit() {
        try {
            // Non-overlapping seeds (exactly touching) that form a long approaching chain.
            Blueprint bp = base(
                new Rules(500, 200, 2, 4, 0, 80, 10),
                List.of(
                    new PuckSeed("a", 100, 100, 80, 0, 10),
                    new PuckSeed("b", 120, 100, 0, 0, 10),
                    new PuckSeed("c", 140, 100, 0, 0, 10),
                    new PuckSeed("d", 160, 100, 0, 0, 10),
                    new PuckSeed("e", 180, 100, 0, 0, 10),
                    new PuckSeed("f", 200, 100, 0, 0, 10),
                    new PuckSeed("g", 220, 100, 0, 0, 10),
                    new PuckSeed("h", 240, 100, 0, 0, 10)
                ),
                List.of(new PaddleSeed("pad", 1, 40, 40, 8, 10, 0, 80, 0, 80)),
                List.of(),
                List.of()
            );
            Engine eng = Engine.start(bp);
            Snapshot before = eng.snapshot();
            try {
                eng.advanceTo(1);
                System.out.println("threw=false");
                printSnap("t1", eng.snapshot());
            } catch (PhysicsException ex) {
                System.out.println("threw=true");
                System.out.println("code=" + ex.code());
                System.out.println("tick=" + ex.tick());
                System.out.println("subframe=" + ex.subframe());
                System.out.println("head=" + eng.headTick());
                System.out.println("unchanged=" + before.equals(eng.snapshot()));
            }
        } catch (BlueprintException ex) {
            System.out.println("blueprint=" + ex.code() + ":" + ex.id());
        }
    }

    static void ricochetCap() {
        // subframes=2 => cap floorDiv(2,2)=1. Corner penetration emits left then top WALL;
        // the second WALL exceeds the cap and must throw ricochet-cap transactionally.
        Blueprint bp = base(
            new Rules(200, 200, 2, 4, 0, 40, 10),
            List.of(new PuckSeed("p", 12, 12, -40, -40, 5)),
            List.of(new PaddleSeed("pad", 1, 100, 100, 8, 10, 60, 140, 60, 140)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        Snapshot before = eng.snapshot();
        try {
            eng.advanceTo(1);
            System.out.println("threw=false");
            printSnap("t1", eng.snapshot());
        } catch (PhysicsException ex) {
            System.out.println("threw=true");
            System.out.println("code=" + ex.code());
            System.out.println("tick=" + ex.tick());
            System.out.println("subframe=" + ex.subframe());
            System.out.println("head=" + eng.headTick());
            System.out.println("unchanged=" + before.equals(eng.snapshot()));
        }
    }

    static void homeClamp() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 40, 10),
            List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 70, 100, 8, 13, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.submit(new InputFrame(1, 0, 1, Action.NORTHEAST));
        eng.advanceTo(1);
        printSnap("t1", eng.snapshot());
    }

    static void friction() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 3, 40, 10),
            List.of(new PuckSeed("p", 100, 100, 10, -7, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        eng.submit(new InputFrame(1, 0, 1, Action.NORTH));
        eng.advanceTo(1);
        printSnap("t1", eng.snapshot());
    }

    static void chunked() {
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            List.of(new PuckSeed("p", 100, 100, 7, -3, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine a = Engine.start(bp);
        a.submit(new InputFrame(1, 0, 1, Action.EAST));
        a.submit(new InputFrame(1, 1, 1, Action.NORTH));
        List<GlideFrame> one = a.advanceTo(4);

        Engine b = Engine.start(bp);
        b.submit(new InputFrame(1, 0, 1, Action.EAST));
        b.submit(new InputFrame(1, 1, 1, Action.NORTH));
        List<GlideFrame> two = new ArrayList<>();
        two.addAll(b.advanceTo(2));
        two.addAll(b.advanceTo(4));
        System.out.println("equal=" + one.equals(two));
        System.out.println("snapEqual=" + a.snapshot().equals(b.snapshot()));
    }

    static void permute() {
        Rules rules = new Rules(200, 200, 4, 8, 0, 20, 10);
        Blueprint a = new Blueprint(
            rules,
            List.of(new PuckSeed("p1", 80, 100, 2, 0, 5), new PuckSeed("p2", 120, 100, -2, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(new Bumper("b2", 100, 60, 6, 0), new Bumper("b1", 100, 140, 6, 0)),
            List.of(),
            List.of(new Goal("gr", Side.RIGHT, 40, 160), new Goal("gl", Side.LEFT, 40, 160))
        );
        Blueprint b = new Blueprint(
            rules,
            List.of(new PuckSeed("p2", 120, 100, -2, 0, 5), new PuckSeed("p1", 80, 100, 2, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(new Bumper("b1", 100, 140, 6, 0), new Bumper("b2", 100, 60, 6, 0)),
            List.of(),
            List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
        );
        Engine ea = Engine.start(a);
        Engine eb = Engine.start(b);
        ea.advanceTo(3);
        eb.advanceTo(3);
        System.out.println("equal=" + ea.snapshot().equals(eb.snapshot()));
    }

    static void mutate() {
        List<PuckSeed> pucks = new ArrayList<>();
        pucks.add(new PuckSeed("p", 100, 100, 4, 0, 5));
        Blueprint bp = base(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            pucks,
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of()
        );
        Engine eng = Engine.start(bp);
        pucks.clear();
        Snapshot s0 = eng.snapshot();
        eng.advanceTo(1);
        Snapshot s1 = eng.snapshot();
        try {
            s1.pucks().clear();
            System.out.println("snapMut=true");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapMut=false");
        }
        System.out.println("survived=" + (s0.pucks().size() == 1 && eng.snapshot().pucks().size() == 1));
        InputReceipt r = eng.submit(new InputFrame(1, 5, 1, Action.WEST));
        try {
            r.corrections().clear();
            System.out.println("receiptMut=true");
        } catch (UnsupportedOperationException ex) {
            System.out.println("receiptMut=false");
        }
    }
}
