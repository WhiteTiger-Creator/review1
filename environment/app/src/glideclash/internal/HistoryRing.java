package glideclash.internal;

import glideclash.api.Action;
import glideclash.api.GlideFrame;
import glideclash.api.PendingServe;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class HistoryRing {
    public static final class BeginState {
        public final long tick;
        public final int leftScore;
        public final int rightScore;
        public final List<MutableBody> paddles;
        public final Map<String, MutableBody> pucks;
        public final List<PendingServe> pendingServes;
        public final Map<Integer, Action> lastEffective;
        public final Map<Integer, Action> publishedActions;
        public GlideFrame published;

        public BeginState(
            long tick, int leftScore, int rightScore,
            List<MutableBody> paddles, Map<String, MutableBody> pucks,
            List<PendingServe> pendingServes,
            Map<Integer, Action> lastEffective,
            Map<Integer, Action> publishedActions
        ) {
            this.tick = tick;
            this.leftScore = leftScore;
            this.rightScore = rightScore;
            this.paddles = paddles;
            this.pucks = pucks;
            this.pendingServes = pendingServes;
            this.lastEffective = lastEffective;
            this.publishedActions = publishedActions;
            this.published = null;
        }

        public BeginState copy() {
            List<MutableBody> pad = new ArrayList<>();
            for (MutableBody b : paddles) {
                pad.add(b.copy());
            }
            Map<String, MutableBody> pk = new HashMap<>();
            for (Map.Entry<String, MutableBody> e : pucks.entrySet()) {
                pk.put(e.getKey(), e.getValue().copy());
            }
            BeginState c = new BeginState(
                tick, leftScore, rightScore, pad, pk,
                new ArrayList<>(pendingServes),
                new TreeMap<>(lastEffective),
                new TreeMap<>(publishedActions)
            );
            c.published = published;
            return c;
        }
    }

    private final int window;
    private final TreeMap<Long, BeginState> begins = new TreeMap<>();
    private ActionBaseline baseline = new ActionBaseline();

    public static final class ActionBaseline {
        public final Map<Integer, Action> beforeOldest = new TreeMap<>();

        public ActionBaseline copy() {
            ActionBaseline c = new ActionBaseline();
            c.beforeOldest.putAll(beforeOldest);
            return c;
        }
    }

    public HistoryRing(int window) {
        this.window = window;
    }

    public HistoryRing copy() {
        HistoryRing c = new HistoryRing(window);
        for (Map.Entry<Long, BeginState> e : begins.entrySet()) {
            c.begins.put(e.getKey(), e.getValue().copy());
        }
        c.baseline = baseline.copy();
        return c;
    }

    public void replaceFrom(HistoryRing o) {
        begins.clear();
        for (Map.Entry<Long, BeginState> e : o.begins.entrySet()) {
            begins.put(e.getKey(), e.getValue().copy());
        }
        baseline = o.baseline.copy();
    }

    public void captureBegin(EngineState state) {
        List<MutableBody> pad = new ArrayList<>();
        for (MutableBody b : state.paddles) {
            pad.add(b.copy());
        }
        Map<String, MutableBody> pk = new HashMap<>();
        for (String id : state.puckIds) {
            pk.put(id, state.puckById.get(id).copy());
        }
        BeginState bs = new BeginState(
            state.headTick, state.leftScore, state.rightScore,
            pad, pk, new ArrayList<>(state.pendingServes),
            new TreeMap<>(state.lastEffective),
            new TreeMap<>(state.publishedActions)
        );
        begins.put(state.headTick, bs);
        prune(state.headTick, state);
    }

    public void setPublished(long tick, GlideFrame frame) {
        BeginState bs = begins.get(tick);
        if (bs != null) {
            bs.published = frame;
        }
    }

    public BeginState get(long tick) {
        return begins.get(tick);
    }

    public GlideFrame published(long tick) {
        BeginState bs = begins.get(tick);
        return bs == null ? null : bs.published;
    }

    public ActionBaseline baseline() {
        return baseline;
    }

    private void prune(long head, EngineState state) {
        long keepFrom = Math.max(0L, head - window + 1);
        while (!begins.isEmpty() && begins.firstKey() < keepFrom) {
            long old = begins.firstKey();
            BeginState removed = begins.remove(old);
            if (begins.isEmpty() || begins.firstKey() > old) {
                baseline.beforeOldest.clear();
                baseline.beforeOldest.putAll(removed.lastEffective);
            }
        }
        // Also drop auth older than keepFrom - 1? Spec: retain beginning for acceptable
        // rollback ticks plus last effective before oldest retained. Auth for ticks
        // still needed for prediction within window.
        Long firstAuth = state.authByTick.isEmpty() ? null : state.authByTick.firstKey();
        while (firstAuth != null && firstAuth < keepFrom) {
            // Keep auth at keepFrom and later; inputs before window may still matter
            // only through baseline. Safe to remove auth strictly older than keepFrom.
            state.authByTick.remove(firstAuth);
            firstAuth = state.authByTick.isEmpty() ? null : state.authByTick.firstKey();
        }
    }

    public boolean canRollback(long tick, long head) {
        return tick >= Math.max(0L, head - window);
    }
}
