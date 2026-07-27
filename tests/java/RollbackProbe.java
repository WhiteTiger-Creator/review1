import glideclash.api.Action;
import glideclash.api.Blueprint;
import glideclash.api.Engine;
import glideclash.api.GlideFrame;
import glideclash.api.Goal;
import glideclash.api.InputFrame;
import glideclash.api.InputReceipt;
import glideclash.api.InputStatus;
import glideclash.api.PaddleSeed;
import glideclash.api.PuckSeed;
import glideclash.api.Rules;
import glideclash.api.Side;
import glideclash.api.Snapshot;
import java.util.List;

public final class RollbackProbe {
    private RollbackProbe() {}

    public static void main(String[] args) {
        if (args.length < 1) {
            throw new IllegalArgumentException("scenario");
        }
        switch (args[0]) {
            case "late-revise" -> lateRevise();
            case "cap-predict" -> capPredict();
            case "sequence" -> sequence();
            case "higher-keep-future" -> higherKeepFuture();
            case "too-old" -> tooOld();
            case "fork" -> fork();
            case "corrections-filter" -> correctionsFilter();
            case "locale-fs" -> localeFs();
            default -> throw new IllegalArgumentException(args[0]);
        }
    }

    static Blueprint bp() {
        return new Blueprint(
            new Rules(200, 200, 4, 8, 0, 20, 10),
            List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of(),
            List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
        );
    }

    static void lateRevise() {
        Engine eng = Engine.start(bp());
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        eng.advanceTo(3);
        Snapshot before = eng.snapshot();
        int padxBefore = before.paddles().get(0).x();
        InputReceipt r = eng.submit(new InputFrame(1, 1, 2, Action.WEST));
        System.out.println("status=" + r.status());
        System.out.println("corrCount=" + r.corrections().size());
        for (GlideFrame f : r.corrections()) {
            System.out.println("corr.tick=" + f.tick() + " corrected=" + f.corrected());
        }
        System.out.println("head=" + eng.headTick());
        System.out.println("padx=" + eng.snapshot().paddles().get(0).x());
        System.out.println("changed=" + (eng.snapshot().paddles().get(0).x() != padxBefore));
    }

    static void capPredict() {
        Engine eng = Engine.start(bp());
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        eng.submit(new InputFrame(1, 2, 1, Action.NORTH));
        eng.advanceTo(4);
        // revise tick 0 to WEST — should affect 0 and 1 but tick 2+ still NORTH
        InputReceipt r = eng.submit(new InputFrame(1, 0, 2, Action.WEST));
        System.out.println("status=" + r.status());
        for (GlideFrame f : r.corrections()) {
            System.out.println("corr." + f.tick() + ".act="
                + f.snapshot().actions().get(0).action());
        }
        // Also print current published history via fork advance from scratch comparison
        Engine fresh = Engine.start(bp());
        fresh.submit(new InputFrame(1, 0, 2, Action.WEST));
        fresh.submit(new InputFrame(1, 2, 1, Action.NORTH));
        List<GlideFrame> frames = fresh.advanceTo(4);
        for (GlideFrame f : frames) {
            System.out.println("fresh." + f.tick() + ".act="
                + f.snapshot().actions().get(0).action());
        }
        System.out.println("match=" + eng.snapshot().equals(fresh.snapshot()));
    }

    static void sequence() {
        Engine eng = Engine.start(bp());
        InputReceipt a = eng.submit(new InputFrame(1, 0, 5, Action.EAST));
        InputReceipt b = eng.submit(new InputFrame(1, 0, 5, Action.EAST));
        InputReceipt c = eng.submit(new InputFrame(1, 0, 4, Action.WEST));
        InputReceipt d = eng.submit(new InputFrame(1, 0, 5, Action.WEST));
        System.out.println("a=" + a.status());
        System.out.println("b=" + b.status());
        System.out.println("c=" + c.status());
        System.out.println("d=" + d.status());
        eng.advanceTo(1);
        System.out.println("act=" + eng.snapshot().actions().get(0).action());
        System.out.println("padx=" + eng.snapshot().paddles().get(0).x());
    }

    static void higherKeepFuture() {
        Engine eng = Engine.start(bp());
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        eng.submit(new InputFrame(1, 2, 1, Action.NORTH));
        eng.advanceTo(1);
        InputReceipt r = eng.submit(new InputFrame(1, 0, 9, Action.WEST));
        System.out.println("status=" + r.status());
        eng.advanceTo(3);
        System.out.println("act2=" + eng.snapshot().actions().get(0).action());
        // After tick 2 completed, actions in snapshot are for tick 2
        Engine check = Engine.start(bp());
        check.submit(new InputFrame(1, 0, 9, Action.WEST));
        check.submit(new InputFrame(1, 2, 1, Action.NORTH));
        List<GlideFrame> frames = check.advanceTo(3);
        System.out.println("t0=" + frames.get(0).snapshot().actions().get(0).action());
        System.out.println("t1=" + frames.get(1).snapshot().actions().get(0).action());
        System.out.println("t2=" + frames.get(2).snapshot().actions().get(0).action());
    }

    static void tooOld() {
        Blueprint wide = new Blueprint(
            new Rules(200, 200, 4, 2, 0, 20, 10),
            List.of(new PuckSeed("p", 100, 100, 0, 0, 5)),
            List.of(new PaddleSeed("pad", 1, 40, 100, 8, 10, 0, 80, 20, 180)),
            List.of(),
            List.of(),
            List.of(new Goal("gl", Side.LEFT, 40, 160), new Goal("gr", Side.RIGHT, 40, 160))
        );
        Engine eng = Engine.start(wide);
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        eng.advanceTo(5);
        Snapshot before = eng.snapshot();
        InputReceipt r = eng.submit(new InputFrame(1, 0, 2, Action.WEST));
        System.out.println("status=" + r.status());
        System.out.println("unchanged=" + before.equals(eng.snapshot()));
        System.out.println("corr=" + r.corrections().size());
    }

    static void fork() {
        Engine parent = Engine.start(bp());
        parent.submit(new InputFrame(1, 0, 1, Action.EAST));
        parent.advanceTo(2);
        Engine child = parent.fork();
        child.submit(new InputFrame(1, 2, 1, Action.WEST));
        child.advanceTo(4);
        parent.submit(new InputFrame(1, 2, 1, Action.NORTH));
        parent.advanceTo(4);
        System.out.println("independent=" + !parent.snapshot().equals(child.snapshot()));
        System.out.println("parent.act=" + parent.snapshot().actions().get(0).action());
        System.out.println("child.act=" + child.snapshot().actions().get(0).action());
        System.out.println("parent.padx=" + parent.snapshot().paddles().get(0).x());
        System.out.println("child.padx=" + child.snapshot().paddles().get(0).x());
    }

    static void correctionsFilter() {
        Engine eng = Engine.start(bp());
        eng.submit(new InputFrame(1, 0, 1, Action.NEUTRAL));
        eng.advanceTo(3);
        // Revise with same effective NEUTRAL via higher sequence but same action — still REVISED
        // Better: revise a tick that doesn't change physics
        InputReceipt same = eng.submit(new InputFrame(1, 1, 2, Action.NEUTRAL));
        System.out.println("same.status=" + same.status());
        System.out.println("same.corr=" + same.corrections().size());
        for (GlideFrame f : same.corrections()) {
            System.out.println("same.corr.tick=" + f.tick() + " corrected=" + f.corrected());
        }
        // Now revise to something that changes
        InputReceipt changed = eng.submit(new InputFrame(1, 1, 3, Action.EAST));
        System.out.println("chg.status=" + changed.status());
        System.out.println("chg.corr=" + changed.corrections().size());
        for (GlideFrame f : changed.corrections()) {
            System.out.println("chg.corr.tick=" + f.tick() + " corrected=" + f.corrected());
            if (!f.corrected()) {
                System.out.println("badCorrectedFlag=true");
            }
        }
    }

    static void localeFs() {
        String cwd = System.getProperty("user.dir");
        String locale = java.util.Locale.getDefault().toString();
        Engine eng = Engine.start(bp());
        eng.submit(new InputFrame(1, 0, 1, Action.EAST));
        List<GlideFrame> frames = eng.advanceTo(2);
        System.out.println("cwdLen=" + cwd.length());
        System.out.println("locale=" + locale);
        System.out.println("head=" + eng.headTick());
        System.out.println("padx=" + eng.snapshot().paddles().get(0).x());
        System.out.println("frame0=" + frames.get(0).tick() + ":" + frames.get(0).corrected());
        System.out.println("record=" + eng.snapshot().toString());
    }
}
