package glideclash.internal;

import glideclash.api.EventKind;

public final class Contact {
    public enum Target { BUMPER, PADDLE, PUCK }

    public final Target target;
    public final MutableBody puckA;
    public final MutableBody puckB;
    public final MutableBody paddle;
    public final String staticId;
    public final int staticX;
    public final int staticY;
    public final int staticRadius;
    public final int kick;
    public final boolean xAxis;
    public final int orient; // -1 means A/negative side, +1 positive

    private Contact(
        Target target, MutableBody puckA, MutableBody puckB, MutableBody paddle,
        String staticId, int staticX, int staticY, int staticRadius, int kick,
        boolean xAxis, int orient
    ) {
        this.target = target;
        this.puckA = puckA;
        this.puckB = puckB;
        this.paddle = paddle;
        this.staticId = staticId;
        this.staticX = staticX;
        this.staticY = staticY;
        this.staticRadius = staticRadius;
        this.kick = kick;
        this.xAxis = xAxis;
        this.orient = orient;
    }

    public static Contact bumper(MutableBody puck, String id, int x, int y, int r, int kick) {
        AxisPick pick = pickAxis(puck.x, puck.y, x, y, puck.id, id);
        return new Contact(Target.BUMPER, puck, null, null, id, x, y, r, kick, pick.xAxis, pick.orient);
    }

    public static Contact paddle(MutableBody puck, MutableBody paddle) {
        AxisPick pick = pickAxis(puck.x, puck.y, paddle.x, paddle.y, puck.id, paddle.id);
        return new Contact(
            Target.PADDLE, puck, null, paddle, paddle.id,
            paddle.x, paddle.y, paddle.radius, 0, pick.xAxis, pick.orient
        );
    }

    public static Contact puck(MutableBody a, MutableBody b) {
        MutableBody lo = a.id.compareTo(b.id) <= 0 ? a : b;
        MutableBody hi = a.id.compareTo(b.id) <= 0 ? b : a;
        AxisPick pick = pickAxis(lo.x, lo.y, hi.x, hi.y, lo.id, hi.id);
        return new Contact(Target.PUCK, lo, hi, null, null, 0, 0, 0, 0, pick.xAxis, pick.orient);
    }

    public EventKind kind() {
        return switch (target) {
            case BUMPER -> EventKind.BUMPER;
            case PADDLE -> EventKind.PADDLE;
            case PUCK -> EventKind.PUCK;
        };
    }

    public String primaryId() {
        if (target == Target.PUCK) {
            return puckA.id;
        }
        return puckA.id;
    }

    public String secondaryId() {
        if (target == Target.PUCK) {
            return puckB.id;
        }
        return staticId;
    }

    public static final class AxisPick {
        public final boolean xAxis;
        public final int orient;

        public AxisPick(boolean xAxis, int orient) {
            this.xAxis = xAxis;
            this.orient = orient;
        }
    }

    public static AxisPick pickAxis(int x1, int y1, int x2, int y2, String id1, String id2) {
        long dx = Math.abs((long) x1 - x2);
        long dy = Math.abs((long) y1 - y2);
        boolean xAxis = dx >= dy;
        int orient;
        if (x1 == x2 && y1 == y2) {
            // Equal centers: X axis, orient negative-to-positive by identifier order
            xAxis = true;
            orient = id1.compareTo(id2) <= 0 ? -1 : 1;
            // For equal centers, id1 is the body being oriented from; use lexical: smaller id is negative
            orient = -1;
        } else if (xAxis) {
            orient = x1 <= x2 ? -1 : 1;
            // orient: direction from body1 toward body2 along axis? Spec: orient negative-to-positive by identifier for equals
            // For separation: move along selected axis until separation equals radii sum
            orient = Integer.compare(x1, x2) <= 0 ? -1 : 1;
            if (x1 == x2) {
                orient = id1.compareTo(id2) <= 0 ? -1 : 1;
            }
        } else {
            orient = Integer.compare(y1, y2) <= 0 ? -1 : 1;
            if (y1 == y2) {
                orient = id1.compareTo(id2) <= 0 ? -1 : 1;
            }
        }
        return new AxisPick(xAxis, orient);
    }

    public static boolean overlaps(MutableBody a, int bx, int by, int br) {
        long dx = (long) a.x - bx;
        long dy = (long) a.y - by;
        long sum = (long) a.radius + br;
        return dx * dx + dy * dy < sum * sum;
    }

    public static boolean overlaps(MutableBody a, MutableBody b) {
        return overlaps(a, b.x, b.y, b.radius);
    }
}
