package glideclash.internal;

import glideclash.api.Action;

public final class Predictor {
    private Predictor() {}

    public static Action effective(EngineState state, int player, long tick) {
        EngineState.AuthSlot slot = state.auth(player, tick);
        if (slot != null) {
            return slot.action;
        }
        // Walk backward for last authoritative action, else lastEffective / baseline
        for (long t = tick - 1; t >= 0; t--) {
            EngineState.AuthSlot prev = state.auth(player, t);
            if (prev != null) {
                return prev.action;
            }
            if (state.history.get(t) == null && t < oldestRetained(state)) {
                break;
            }
        }
        Action fromLast = state.lastEffective.get(player);
        if (fromLast != null) {
            return fromLast;
        }
        Action base = state.history.baseline().beforeOldest.get(player);
        return base == null ? Action.NEUTRAL : base;
    }

    private static long oldestRetained(EngineState state) {
        long keepFrom = Math.max(0L, state.headTick - state.rules.rollbackWindow());
        return keepFrom;
    }

    public static int axisX(Action a) {
        return switch (a) {
            case WEST, NORTHWEST, SOUTHWEST -> -1;
            case EAST, NORTHEAST, SOUTHEAST -> 1;
            default -> 0;
        };
    }

    public static int axisY(Action a) {
        return switch (a) {
            case NORTH, NORTHWEST, NORTHEAST -> -1;
            case SOUTH, SOUTHWEST, SOUTHEAST -> 1;
            default -> 0;
        };
    }
}
