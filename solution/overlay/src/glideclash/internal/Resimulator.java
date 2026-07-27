package glideclash.internal;

import glideclash.api.Action;
import glideclash.api.ArenaEvent;
import glideclash.api.GlideFrame;
import glideclash.api.PhysicsException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class Resimulator {
    private Resimulator() {}

    public static GlideFrame simulateOneTick(EngineState state, boolean corrected) {
        state.history.captureBegin(state);
        long tick = state.headTick;
        state.resetTickCounters();

        GoalLogic.respawn(state);

        Map<Integer, Action> actions = InputLedger.chooseActions(state, tick);
        state.publishedActions = new TreeMap<>(actions);
        for (Map.Entry<Integer, Action> e : actions.entrySet()) {
            int player = e.getKey();
            state.lastEffective.put(player, e.getValue());
            state.actionWasAuthoritative.put(player, state.auth(player, tick) != null);
        }

        for (MutableBody pad : state.paddles) {
            Action a = actions.get(pad.player);
            pad.vx = Predictor.axisX(a) * pad.speed;
            pad.vy = Predictor.axisY(a) * pad.speed;
            pad.xRemainder = 0;
            pad.yRemainder = 0;
        }

        List<ArenaEvent> events = new ArrayList<>();
        int subframes = state.rules.subframes();
        for (int sf = 0; sf < subframes; sf++) {
            for (MutableBody pad : state.paddles) {
                Integrator.movePaddle(pad, subframes);
            }
            List<MutableBody> active = state.activePucks();
            List<GoalLogic.Prior> priors = GoalLogic.capturePriors(active);
            for (MutableBody puck : active) {
                Integrator.movePuck(puck, subframes);
            }
            events.addAll(GoalLogic.resolveBoundaries(state, tick, sf, priors));
            try {
                events.addAll(CollisionPass.resolve(state, tick, sf));
            } catch (ArithmeticException ex) {
                throw new PhysicsException("arithmetic", tick, sf);
            }
        }

        for (MutableBody puck : state.activePucks()) {
            puck.vx = Integrator.applyFriction(puck.vx, state.rules.friction());
            puck.vy = Integrator.applyFriction(puck.vy, state.rules.friction());
        }
        for (MutableBody pad : state.paddles) {
            pad.vx = 0;
            pad.vy = 0;
        }

        state.headTick = Math.addExact(state.headTick, 1L);
        GlideFrame frame = new GlideFrame(
            tick, corrected, ImmutableViews.snapshot(state), events
        );
        state.history.setPublished(tick, frame);
        return frame;
    }

    public static List<GlideFrame> rollbackFrom(EngineState state, long fromTick) {
        long formerHead = state.headTick;
        HistoryRing.BeginState begin = state.history.get(fromTick);
        if (begin == null) {
            throw new IllegalStateException("missing history " + fromTick);
        }

        // Restore beginning of fromTick
        state.headTick = begin.tick;
        state.leftScore = begin.leftScore;
        state.rightScore = begin.rightScore;
        state.pendingServes.clear();
        state.pendingServes.addAll(begin.pendingServes);
        state.lastEffective.clear();
        state.lastEffective.putAll(begin.lastEffective);
        state.publishedActions.clear();
        state.publishedActions.putAll(begin.publishedActions);
        for (int i = 0; i < state.paddles.size(); i++) {
            state.paddles.get(i).setFrom(begin.paddles.get(i));
        }
        for (String id : state.puckIds) {
            state.puckById.get(id).setFrom(begin.pucks.get(id));
        }

        // Collect old published frames for comparison
        Map<Long, GlideFrame> oldFrames = new TreeMap<>();
        for (long t = fromTick; t < formerHead; t++) {
            GlideFrame old = state.history.published(t);
            if (old != null) {
                oldFrames.put(t, old);
            }
        }

        List<GlideFrame> corrections = new ArrayList<>();
        while (state.headTick < formerHead) {
            long t = state.headTick;
            GlideFrame neu = simulateOneTick(state, true);
            GlideFrame old = oldFrames.get(t);
            if (old == null
                || !old.snapshot().equals(neu.snapshot())
                || !old.events().equals(neu.events())) {
                corrections.add(neu);
            }
        }
        return List.copyOf(corrections);
    }
}
