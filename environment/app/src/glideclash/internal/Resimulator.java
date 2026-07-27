package glideclash.internal;

import glideclash.api.GlideFrame;
import java.util.List;

public final class Resimulator {
    private Resimulator() {}

    public static GlideFrame simulateOneTick(EngineState state, boolean corrected) {
        state.history.captureBegin(state);
        long tick = state.headTick;
        GoalLogic.respawn(state);

        var actions = InputLedger.chooseActions(state, tick);
        state.publishedActions = new java.util.TreeMap<>(actions);
        for (var e : actions.entrySet()) {
            state.lastEffective.put(e.getKey(), e.getValue());
        }

        for (MutableBody pad : state.paddles) {
            var a = actions.get(pad.player);
            pad.vx = Predictor.axisX(a) * pad.speed;
            pad.vy = Predictor.axisY(a) * pad.speed;
            pad.xRemainder = 0;
            pad.yRemainder = 0;
        }

        java.util.ArrayList<glideclash.api.ArenaEvent> events = new java.util.ArrayList<>();
        int subframes = state.rules.subframes();
        for (int sf = 0; sf < subframes; sf++) {
            for (MutableBody pad : state.paddles) {
                Integrator.movePaddle(pad, subframes);
            }
            var active = state.activePucks();
            var priors = GoalLogic.capturePriors(active);
            for (MutableBody puck : active) {
                Integrator.movePuck(puck, subframes);
            }
            events.addAll(GoalLogic.resolveBoundaries(state, tick, sf, priors));
            events.addAll(CollisionPass.resolve(state, tick, sf));
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
        // Starter: no rollback
        return List.of();
    }
}
