package glideclash.internal;

import glideclash.api.Blueprint;
import glideclash.api.BlueprintException;
import glideclash.api.Bumper;
import glideclash.api.Gate;
import glideclash.api.Goal;
import glideclash.api.PaddleSeed;
import glideclash.api.PuckSeed;
import glideclash.api.Rules;
import glideclash.api.Side;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class BlueprintCheck {
    private static final Pattern ID = Pattern.compile("^[a-z][a-z0-9-]{0,23}$");
    private static final String[] CODE_ORDER = {
        "rules", "duplicate-id", "player", "bounds", "home", "goal", "gate", "overlap", "null-member"
    };

    private BlueprintCheck() {}

    public static void validate(Blueprint bp) {
        Map<String, String> found = new HashMap<>();
        checkNulls(bp, found);
        if (bp.rules() != null) {
            checkRules(bp.rules(), found);
        }
        if (hasLists(bp)) {
            checkIdsPlayers(bp, found);
            checkBounds(bp, found);
            checkHome(bp, found);
            checkGoals(bp, found);
            checkGates(bp, found);
            checkOverlaps(bp, found);
        }
        throwFirst(found);
    }

    private static boolean hasLists(Blueprint bp) {
        return bp.pucks() != null && bp.paddles() != null
            && bp.bumpers() != null && bp.gates() != null && bp.goals() != null;
    }

    private static void checkNulls(Blueprint bp, Map<String, String> found) {
        if (bp.rules() == null || bp.pucks() == null || bp.paddles() == null
            || bp.bumpers() == null || bp.gates() == null || bp.goals() == null) {
            note(found, "null-member", "-");
            return;
        }
        for (PuckSeed p : bp.pucks()) {
            if (p == null) {
                note(found, "null-member", "-");
                return;
            }
        }
        for (PaddleSeed p : bp.paddles()) {
            if (p == null) {
                note(found, "null-member", "-");
                return;
            }
        }
        for (Bumper b : bp.bumpers()) {
            if (b == null) {
                note(found, "null-member", "-");
                return;
            }
        }
        for (Gate g : bp.gates()) {
            if (g == null || g.axis() == null) {
                note(found, "null-member", "-");
                return;
            }
        }
        for (Goal g : bp.goals()) {
            if (g == null || g.side() == null) {
                note(found, "null-member", "-");
                return;
            }
        }
    }

    private static void checkRules(Rules r, Map<String, String> found) {
        int w = r.width();
        int h = r.height();
        if (w < 100 || w > 1_000_000 || h < 100 || h > 1_000_000) {
            note(found, "rules", "-");
            return;
        }
        if (r.subframes() < 2 || r.subframes() > 256) {
            note(found, "rules", "-");
            return;
        }
        if (r.rollbackWindow() < 1 || r.rollbackWindow() > 256) {
            note(found, "rules", "-");
            return;
        }
        if (r.maxSpeed() < 1 || r.maxSpeed() > 100_000) {
            note(found, "rules", "-");
            return;
        }
        int half = Math.min(w, h) / 2;
        if (r.maxSpeed() > half) {
            note(found, "rules", "-");
            return;
        }
        if (r.friction() < 0 || r.friction() > r.maxSpeed()) {
            note(found, "rules", "-");
            return;
        }
        if (r.serveSpeed() < 1 || r.serveSpeed() > r.maxSpeed()) {
            note(found, "rules", "-");
        }
    }

    private static void checkIdsPlayers(Blueprint bp, Map<String, String> found) {
        if (bp.pucks().isEmpty() || bp.paddles().isEmpty() || bp.goals().isEmpty()) {
            note(found, "bounds", "-");
        }
        Set<String> ids = new HashSet<>();
        Set<Integer> players = new HashSet<>();
        collectId(bp.pucks(), ids, found);
        collectId(bp.paddles(), ids, found);
        collectId(bp.bumpers(), ids, found);
        collectId(bp.gates(), ids, found);
        collectId(bp.goals(), ids, found);
        for (PaddleSeed p : bp.paddles()) {
            if (p != null && p.id() != null && ID.matcher(p.id()).matches()) {
                if (p.player() < 1 || p.player() > 8 || !players.add(p.player())) {
                    note(found, "player", p.id());
                }
            }
        }
    }

    private static void collectId(List<?> items, Set<String> ids, Map<String, String> found) {
        for (Object o : items) {
            String id = idOf(o);
            if (id == null) {
                continue;
            }
            if (!ID.matcher(id).matches()) {
                note(found, "bounds", id);
                continue;
            }
            if (!ids.add(id)) {
                note(found, "duplicate-id", id);
            }
        }
    }

    private static String idOf(Object o) {
        if (o instanceof PuckSeed p) {
            return p.id();
        }
        if (o instanceof PaddleSeed p) {
            return p.id();
        }
        if (o instanceof Bumper b) {
            return b.id();
        }
        if (o instanceof Gate g) {
            return g.id();
        }
        if (o instanceof Goal g) {
            return g.id();
        }
        return null;
    }

    private static void checkBounds(Blueprint bp, Map<String, String> found) {
        Rules r = bp.rules();
        int w = r.width();
        int h = r.height();
        int maxR = Math.min(w, h) / 2;
        int maxS = r.maxSpeed();
        for (PuckSeed p : bp.pucks()) {
            if (p == null || !validId(p.id())) {
                continue;
            }
            if (p.radius() < 1 || p.radius() > maxR) {
                note(found, "bounds", p.id());
                continue;
            }
            if (p.vx() < -maxS || p.vx() > maxS || p.vy() < -maxS || p.vy() > maxS) {
                note(found, "bounds", p.id());
                continue;
            }
            if (!circleInside(p.x(), p.y(), p.radius(), w, h)) {
                note(found, "bounds", p.id());
            }
        }
        for (PaddleSeed p : bp.paddles()) {
            if (p == null || !validId(p.id())) {
                continue;
            }
            if (p.radius() < 1 || p.radius() > maxR || p.speed() < 1 || p.speed() > maxS) {
                note(found, "bounds", p.id());
                continue;
            }
            if (!circleInside(p.x(), p.y(), p.radius(), w, h)) {
                note(found, "bounds", p.id());
            }
        }
        for (Bumper b : bp.bumpers()) {
            if (b == null || !validId(b.id())) {
                continue;
            }
            if (b.radius() < 1 || b.radius() > maxR || b.kick() < 0 || b.kick() > maxS) {
                note(found, "bounds", b.id());
                continue;
            }
            if (!circleInside(b.x(), b.y(), b.radius(), w, h)) {
                note(found, "bounds", b.id());
            }
        }
    }

    private static void checkHome(Blueprint bp, Map<String, String> found) {
        Rules r = bp.rules();
        for (PaddleSeed p : bp.paddles()) {
            if (p == null || !validId(p.id())) {
                continue;
            }
            if (!(0 <= p.homeMinX() && p.homeMinX() < p.homeMaxX() && p.homeMaxX() <= r.width())) {
                note(found, "home", p.id());
                continue;
            }
            if (!(0 <= p.homeMinY() && p.homeMinY() < p.homeMaxY() && p.homeMaxY() <= r.height())) {
                note(found, "home", p.id());
                continue;
            }
            int rad = p.radius();
            if (p.x() - rad < p.homeMinX() || p.x() + rad > p.homeMaxX()
                || p.y() - rad < p.homeMinY() || p.y() + rad > p.homeMaxY()) {
                note(found, "home", p.id());
            }
        }
    }

    private static void checkGoals(Blueprint bp, Map<String, String> found) {
        Rules r = bp.rules();
        int left = 0;
        int right = 0;
        for (Goal g : bp.goals()) {
            if (g == null || !validId(g.id())) {
                continue;
            }
            if (!(0 <= g.low() && g.low() < g.high() && g.high() <= r.height())) {
                note(found, "goal", g.id());
            }
            if (g.side() == Side.LEFT) {
                left++;
            } else if (g.side() == Side.RIGHT) {
                right++;
            }
        }
        if (left != 1 || right != 1) {
            String id = "-";
            for (Goal g : bp.goals()) {
                if (validId(g.id()) && (id.equals("-") || g.id().compareTo(id) < 0)) {
                    id = g.id();
                }
            }
            note(found, "goal", id);
        }
    }

    private static void checkGates(Blueprint bp, Map<String, String> found) {
        Rules r = bp.rules();
        for (Gate g : bp.gates()) {
            if (g == null || g.axis() == null || !validId(g.id())) {
                continue;
            }
            if (g.blockedSign() != -1 && g.blockedSign() != 1) {
                note(found, "gate", g.id());
                continue;
            }
            if (g.axis() == glideclash.api.Axis.X) {
                if (g.coordinate() < 1 || g.coordinate() > r.width() - 1) {
                    note(found, "gate", g.id());
                    continue;
                }
                if (!(0 <= g.low() && g.low() < g.high() && g.high() <= r.height())) {
                    note(found, "gate", g.id());
                }
            } else {
                if (g.coordinate() < 1 || g.coordinate() > r.height() - 1) {
                    note(found, "gate", g.id());
                    continue;
                }
                if (!(0 <= g.low() && g.low() < g.high() && g.high() <= r.width())) {
                    note(found, "gate", g.id());
                }
            }
        }
    }

    private static void checkOverlaps(Blueprint bp, Map<String, String> found) {
        record Circ(String id, int x, int y, int r) {}
        java.util.ArrayList<Circ> circles = new java.util.ArrayList<>();
        for (PuckSeed p : bp.pucks()) {
            if (p != null && validId(p.id())) {
                circles.add(new Circ(p.id(), p.x(), p.y(), p.radius()));
            }
        }
        for (PaddleSeed p : bp.paddles()) {
            if (p != null && validId(p.id())) {
                circles.add(new Circ(p.id(), p.x(), p.y(), p.radius()));
            }
        }
        for (Bumper b : bp.bumpers()) {
            if (b != null && validId(b.id())) {
                circles.add(new Circ(b.id(), b.x(), b.y(), b.radius()));
            }
        }
        circles.sort((a, b) -> a.id.compareTo(b.id));
        for (int i = 0; i < circles.size(); i++) {
            for (int j = i + 1; j < circles.size(); j++) {
                Circ a = circles.get(i);
                Circ b = circles.get(j);
                if (overlap(a.x, a.y, a.r, b.x, b.y, b.r)) {
                    note(found, "overlap", a.id.compareTo(b.id) <= 0 ? a.id : b.id);
                }
            }
        }
        for (Circ c : circles) {
            for (Gate g : bp.gates()) {
                if (g == null || !validId(g.id())) {
                    continue;
                }
                if (intersectsGate(c.x, c.y, c.r, g)) {
                    note(found, "overlap", c.id.compareTo(g.id()) <= 0 ? c.id : g.id());
                }
            }
        }
    }

    private static boolean intersectsGate(int x, int y, int r, Gate g) {
        if (g.axis() == glideclash.api.Axis.X) {
            long dx = Math.abs((long) x - g.coordinate());
            if (dx > r) {
                return false;
            }
            int lo = g.low();
            int hi = g.high();
            return y + r >= lo && y - r <= hi;
        }
        long dy = Math.abs((long) y - g.coordinate());
        if (dy > r) {
            return false;
        }
        return x + r >= g.low() && x - r <= g.high();
    }

    private static boolean overlap(int x1, int y1, int r1, int x2, int y2, int r2) {
        long dx = (long) x1 - x2;
        long dy = (long) y1 - y2;
        long sum = (long) r1 + r2;
        return dx * dx + dy * dy < sum * sum;
    }

    private static boolean circleInside(int x, int y, int r, int w, int h) {
        return x - r >= 0 && y - r >= 0 && x + r <= w && y + r <= h;
    }

    private static boolean validId(String id) {
        return id != null && ID.matcher(id).matches();
    }

    private static void note(Map<String, String> found, String code, String id) {
        String prev = found.get(code);
        if (prev == null || id.compareTo(prev) < 0) {
            found.put(code, id);
        }
    }

    private static void throwFirst(Map<String, String> found) {
        for (String code : CODE_ORDER) {
            if (found.containsKey(code)) {
                throw new BlueprintException(code, found.get(code));
            }
        }
    }
}
