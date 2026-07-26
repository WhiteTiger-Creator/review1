package glideclash.internal;

import glideclash.api.Action;

public final class Predictor {
    private Predictor() {}

    public static Action effective(EngineState state, int player, long tick) {
        // Starter: only exact-tick authority; no prediction propagation
        EngineState.AuthSlot slot = state.auth(player, tick);
        if (slot != null) {
            return slot.action;
        }
        return Action.NEUTRAL;
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
