package glideclash.internal;

import glideclash.api.ArenaEvent;
import java.util.ArrayList;
import java.util.List;

public final class GoalLogic {
    private GoalLogic() {}

    public static final class Prior {
        public final String id;
        public final int x;
        public final int y;

        public Prior(String id, int x, int y) {
            this.id = id;
            this.x = x;
            this.y = y;
        }
    }

    public static List<Prior> capturePriors(List<MutableBody> pucks) {
        List<Prior> out = new ArrayList<>();
        for (MutableBody p : pucks) {
            out.add(new Prior(p.id, p.x, p.y));
        }
        return out;
    }

    public static List<ArenaEvent> resolveBoundaries(
        EngineState state, long tick, int subframe, List<Prior> priors
    ) {
        // Starter: goals, walls, and gates omitted
        return List.of();
    }

    public static void respawn(EngineState state) {
        // Starter: no respawn
    }
}
