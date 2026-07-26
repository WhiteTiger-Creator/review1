package glideclash.internal;

import glideclash.api.ArenaEvent;
import glideclash.api.EventKind;
import glideclash.api.Gate;
import glideclash.api.PendingServe;
import glideclash.api.Side;
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
        List<ArenaEvent> events = new ArrayList<>();
        for (MutableBody puck : new ArrayList<>(state.activePucks())) {
            Prior prior = null;
            for (Prior p : priors) {
                if (p.id.equals(puck.id)) {
                    prior = p;
                    break;
                }
            }
            int px = prior == null ? puck.x : prior.x;
            int py = prior == null ? puck.y : prior.y;

            if (puck.x - puck.radius < 0
                && inGoalY(puck.y, state.leftGoal.low(), state.leftGoal.high())) {
                events.add(new ArenaEvent(tick, subframe, EventKind.GOAL, puck.id, state.leftGoal.id()));
                state.rightScore = Math.toIntExact(Math.addExact(state.rightScore, 1));
                puck.active = false;
                state.pendingServes.add(new PendingServe(puck.id, Side.LEFT));
                continue;
            }
            if (puck.x + puck.radius > state.rules.width()
                && inGoalY(puck.y, state.rightGoal.low(), state.rightGoal.high())) {
                events.add(new ArenaEvent(tick, subframe, EventKind.GOAL, puck.id, state.rightGoal.id()));
                state.leftScore = Math.toIntExact(Math.addExact(state.leftScore, 1));
                puck.active = false;
                state.pendingServes.add(new PendingServe(puck.id, Side.RIGHT));
                continue;
            }

            events.addAll(resolveWalls(state, tick, subframe, puck));

            for (Gate g : state.gates) {
                if (blockedByGate(puck, px, py, g)) {
                    if (g.axis() == glideclash.api.Axis.X) {
                        puck.x = g.coordinate() - g.blockedSign() * puck.radius;
                        puck.vx = -puck.vx;
                        puck.xRemainder = 0;
                    } else {
                        puck.y = g.coordinate() - g.blockedSign() * puck.radius;
                        puck.vy = -puck.vy;
                        puck.yRemainder = 0;
                    }
                    ArenaEvent ge = new ArenaEvent(tick, subframe, EventKind.GATE, puck.id, g.id());
                    events.add(ge);
                    state.noteRicochet(puck.id, tick, subframe);
                    // After GATE, immediately re-run walls for this puck only.
                    events.addAll(resolveWalls(state, tick, subframe, puck));
                }
            }
        }
        return events;
    }

    private static List<ArenaEvent> resolveWalls(
        EngineState state, long tick, int subframe, MutableBody puck
    ) {
        List<ArenaEvent> events = new ArrayList<>();
        int w = state.rules.width();
        int h = state.rules.height();
        int r = puck.radius;
        if (puck.x - r < 0) {
            puck.x = r;
            if (puck.vx < 0) {
                puck.vx = -puck.vx;
            }
            puck.xRemainder = 0;
            events.add(new ArenaEvent(tick, subframe, EventKind.WALL, puck.id, "left"));
            state.noteRicochet(puck.id, tick, subframe);
        } else if (puck.x + r > w) {
            puck.x = w - r;
            if (puck.vx > 0) {
                puck.vx = -puck.vx;
            }
            puck.xRemainder = 0;
            events.add(new ArenaEvent(tick, subframe, EventKind.WALL, puck.id, "right"));
            state.noteRicochet(puck.id, tick, subframe);
        }
        if (puck.y - r < 0) {
            puck.y = r;
            if (puck.vy < 0) {
                puck.vy = -puck.vy;
            }
            puck.yRemainder = 0;
            events.add(new ArenaEvent(tick, subframe, EventKind.WALL, puck.id, "top"));
            state.noteRicochet(puck.id, tick, subframe);
        } else if (puck.y + r > h) {
            puck.y = h - r;
            if (puck.vy > 0) {
                puck.vy = -puck.vy;
            }
            puck.yRemainder = 0;
            events.add(new ArenaEvent(tick, subframe, EventKind.WALL, puck.id, "bottom"));
            state.noteRicochet(puck.id, tick, subframe);
        }
        return events;
    }

    private static boolean inGoalY(int y, int low, int high) {
        return y >= low && y <= high;
    }

    private static boolean blockedByGate(MutableBody puck, int prevX, int prevY, Gate g) {
        if (g.axis() == glideclash.api.Axis.X) {
            int coord = g.coordinate();
            boolean crossed = g.blockedSign() == 1
                ? prevX < coord && puck.x >= coord
                : prevX > coord && puck.x <= coord;
            if (!crossed) {
                return false;
            }
            return puck.y >= g.low() - puck.radius && puck.y <= g.high() + puck.radius;
        }
        int coord = g.coordinate();
        boolean crossed = g.blockedSign() == 1
            ? prevY < coord && puck.y >= coord
            : prevY > coord && puck.y <= coord;
        if (!crossed) {
            return false;
        }
        return puck.x >= g.low() - puck.radius && puck.x <= g.high() + puck.radius;
    }

    public static void respawn(EngineState state) {
        if (state.pendingServes.isEmpty()) {
            return;
        }
        List<PendingServe> serves = new ArrayList<>(state.pendingServes);
        serves.sort((a, b) -> a.puckId().compareTo(b.puckId()));
        state.pendingServes.clear();
        int cx = state.rules.width() / 2;
        int cy = state.rules.height() / 2;
        for (PendingServe s : serves) {
            MutableBody puck = state.puckById.get(s.puckId());
            puck.x = cx;
            puck.y = cy;
            puck.xRemainder = 0;
            puck.yRemainder = 0;
            puck.vy = 0;
            // Away from the exited mouth.
            puck.vx = s.exitedSide() == Side.LEFT
                ? state.rules.serveSpeed()
                : -state.rules.serveSpeed();
            puck.active = true;
        }
    }
}
