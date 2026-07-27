package glideclash.internal;

import glideclash.api.Action;
import glideclash.api.Blueprint;
import glideclash.api.Bumper;
import glideclash.api.Gate;
import glideclash.api.GlideFrame;
import glideclash.api.Goal;
import glideclash.api.PaddleSeed;
import glideclash.api.PendingServe;
import glideclash.api.PuckSeed;
import glideclash.api.Rules;
import glideclash.api.Side;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class EngineState {
    public final Rules rules;
    public final List<Bumper> bumpers;
    public final List<Gate> gates;
    public final Goal leftGoal;
    public final Goal rightGoal;
    public final List<MutableBody> paddles;
    public final Map<String, MutableBody> puckById;
    public final List<String> puckIds;
    public final List<Integer> players;

    public long headTick;
    public int leftScore;
    public int rightScore;
    public final List<PendingServe> pendingServes;
    public final Map<Integer, Action> lastEffective;
    public final TreeMap<Long, Map<Integer, AuthSlot>> authByTick;
    public final HistoryRing history;
    public Map<Integer, Action> publishedActions;
    /** player -> whether this tick's chosen action came from a stored InputFrame */
    public final Map<Integer, Boolean> actionWasAuthoritative;
    public int bumperResponseOrdinal;
    public final Map<String, Integer> ricochetByPuck;

    public static final class AuthSlot {
        public final long sequence;
        public final Action action;

        public AuthSlot(long sequence, Action action) {
            this.sequence = sequence;
            this.action = action;
        }
    }

    private EngineState(
        Rules rules, List<Bumper> bumpers, List<Gate> gates,
        Goal leftGoal, Goal rightGoal,
        List<MutableBody> paddles, Map<String, MutableBody> puckById, List<String> puckIds,
        List<Integer> players, long headTick, int leftScore, int rightScore,
        List<PendingServe> pendingServes, Map<Integer, Action> lastEffective,
        TreeMap<Long, Map<Integer, AuthSlot>> authByTick, HistoryRing history,
        Map<Integer, Action> publishedActions,
        Map<Integer, Boolean> actionWasAuthoritative,
        int bumperResponseOrdinal,
        Map<String, Integer> ricochetByPuck
    ) {
        this.rules = rules;
        this.bumpers = bumpers;
        this.gates = gates;
        this.leftGoal = leftGoal;
        this.rightGoal = rightGoal;
        this.paddles = paddles;
        this.puckById = puckById;
        this.puckIds = puckIds;
        this.players = players;
        this.headTick = headTick;
        this.leftScore = leftScore;
        this.rightScore = rightScore;
        this.pendingServes = pendingServes;
        this.lastEffective = lastEffective;
        this.authByTick = authByTick;
        this.history = history;
        this.publishedActions = publishedActions;
        this.actionWasAuthoritative = actionWasAuthoritative;
        this.bumperResponseOrdinal = bumperResponseOrdinal;
        this.ricochetByPuck = ricochetByPuck;
    }

    public static EngineState create(Blueprint bp) {
        Rules rules = bp.rules();
        Goal left = null;
        Goal right = null;
        for (Goal g : bp.goals()) {
            if (g.side() == Side.LEFT) {
                left = g;
            } else {
                right = g;
            }
        }
        List<MutableBody> paddles = new ArrayList<>();
        List<Integer> players = new ArrayList<>();
        Map<Integer, Action> last = new TreeMap<>();
        Map<Integer, Action> published = new TreeMap<>();
        for (PaddleSeed p : bp.paddles()) {
            paddles.add(new MutableBody(
                p.id(), false, p.radius(), p.speed(), p.player(),
                p.homeMinX(), p.homeMaxX(), p.homeMinY(), p.homeMaxY(),
                p.x(), p.y(), 0, 0, 0, 0, true
            ));
            players.add(p.player());
            last.put(p.player(), Action.NEUTRAL);
            published.put(p.player(), Action.NEUTRAL);
        }
        players.sort(Integer::compareTo);
        Map<String, MutableBody> pucks = new LinkedHashMap<>();
        List<String> puckIds = new ArrayList<>();
        for (PuckSeed p : bp.pucks()) {
            puckIds.add(p.id());
            pucks.put(p.id(), new MutableBody(
                p.id(), true, p.radius(), 0, 0, 0, 0, 0, 0,
                p.x(), p.y(), p.vx(), p.vy(), 0, 0, true
            ));
        }
        puckIds.sort(String::compareTo);
        return new EngineState(
            rules,
            List.copyOf(bp.bumpers()),
            List.copyOf(bp.gates()),
            left,
            right,
            paddles,
            pucks,
            puckIds,
            players,
            0L,
            0,
            0,
            new ArrayList<>(),
            last,
            new TreeMap<>(),
            new HistoryRing(rules.rollbackWindow()),
            published,
            new TreeMap<>(),
            0,
            new HashMap<>()
        );
    }

    public void resetTickCounters() {
        bumperResponseOrdinal = 0;
        ricochetByPuck.clear();
        actionWasAuthoritative.clear();
    }

    public void noteRicochet(String puckId, long tick, int subframe) {
        int next = ricochetByPuck.getOrDefault(puckId, 0) + 1;
        ricochetByPuck.put(puckId, next);
        int cap = Math.floorDiv(rules.subframes(), 2);
        if (next > cap) {
            throw new glideclash.api.PhysicsException("ricochet-cap", tick, subframe);
        }
    }

    public EngineState deepCopy() {
        List<MutableBody> padCopy = new ArrayList<>();
        for (MutableBody b : paddles) {
            padCopy.add(b.copy());
        }
        Map<String, MutableBody> puckCopy = new LinkedHashMap<>();
        for (String id : puckIds) {
            puckCopy.put(id, puckById.get(id).copy());
        }
        Map<Integer, Action> lastCopy = new TreeMap<>(lastEffective);
        Map<Integer, Action> pubCopy = new TreeMap<>(publishedActions);
        TreeMap<Long, Map<Integer, AuthSlot>> authCopy = new TreeMap<>();
        for (Map.Entry<Long, Map<Integer, AuthSlot>> e : authByTick.entrySet()) {
            authCopy.put(e.getKey(), new TreeMap<>(e.getValue()));
        }
        return new EngineState(
            rules, bumpers, gates, leftGoal, rightGoal,
            padCopy, puckCopy, new ArrayList<>(puckIds), new ArrayList<>(players),
            headTick, leftScore, rightScore,
            new ArrayList<>(pendingServes), lastCopy, authCopy,
            history.copy(), pubCopy,
            new TreeMap<>(actionWasAuthoritative),
            bumperResponseOrdinal,
            new HashMap<>(ricochetByPuck)
        );
    }

    public void restoreFrom(EngineState o) {
        headTick = o.headTick;
        leftScore = o.leftScore;
        rightScore = o.rightScore;
        pendingServes.clear();
        pendingServes.addAll(o.pendingServes);
        lastEffective.clear();
        lastEffective.putAll(o.lastEffective);
        publishedActions.clear();
        publishedActions.putAll(o.publishedActions);
        authByTick.clear();
        for (Map.Entry<Long, Map<Integer, AuthSlot>> e : o.authByTick.entrySet()) {
            authByTick.put(e.getKey(), new TreeMap<>(e.getValue()));
        }
        history.replaceFrom(o.history);
        for (int i = 0; i < paddles.size(); i++) {
            paddles.get(i).setFrom(o.paddles.get(i));
        }
        for (String id : puckIds) {
            puckById.get(id).setFrom(o.puckById.get(id));
        }
        actionWasAuthoritative.clear();
        actionWasAuthoritative.putAll(o.actionWasAuthoritative);
        bumperResponseOrdinal = o.bumperResponseOrdinal;
        ricochetByPuck.clear();
        ricochetByPuck.putAll(o.ricochetByPuck);
    }

    public List<MutableBody> activePucks() {
        List<MutableBody> out = new ArrayList<>();
        for (String id : puckIds) {
            MutableBody b = puckById.get(id);
            if (b.active) {
                out.add(b);
            }
        }
        return out;
    }

    public AuthSlot auth(int player, long tick) {
        Map<Integer, AuthSlot> m = authByTick.get(tick);
        if (m == null) {
            return null;
        }
        return m.get(player);
    }

    public void putAuth(int player, long tick, long sequence, Action action) {
        authByTick.computeIfAbsent(tick, t -> new TreeMap<>())
            .put(player, new AuthSlot(sequence, action));
    }
}
