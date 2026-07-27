package glideclash.internal;

public final class Integrator {
    private Integrator() {}

    public static void integrateAxis(
        MutableBody body, boolean xAxis, int velocity, int subframes
    ) {
        if (xAxis) {
            long rem = Math.addExact((long) body.xRemainder, velocity);
            int delta = Math.toIntExact(Math.floorDiv(rem, subframes));
            body.xRemainder = Math.toIntExact(Math.floorMod(rem, subframes));
            body.x = Math.toIntExact(Math.addExact((long) body.x, delta));
        } else {
            long rem = Math.addExact((long) body.yRemainder, velocity);
            int delta = Math.toIntExact(Math.floorDiv(rem, subframes));
            body.yRemainder = Math.toIntExact(Math.floorMod(rem, subframes));
            body.y = Math.toIntExact(Math.addExact((long) body.y, delta));
        }
    }

    public static void movePaddle(MutableBody paddle, int subframes) {
        integrateAxis(paddle, true, paddle.vx, subframes);
        integrateAxis(paddle, false, paddle.vy, subframes);
        clampHome(paddle);
    }

    public static void clampHome(MutableBody paddle) {
        int minX = paddle.homeMinX + paddle.radius;
        int maxX = paddle.homeMaxX - paddle.radius;
        int minY = paddle.homeMinY + paddle.radius;
        int maxY = paddle.homeMaxY - paddle.radius;
        if (paddle.x < minX) {
            paddle.x = minX;
            paddle.xRemainder = 0;
        } else if (paddle.x > maxX) {
            paddle.x = maxX;
            paddle.xRemainder = 0;
        }
        if (paddle.y < minY) {
            paddle.y = minY;
            paddle.yRemainder = 0;
        } else if (paddle.y > maxY) {
            paddle.y = maxY;
            paddle.yRemainder = 0;
        }
    }

    public static void movePuck(MutableBody puck, int subframes) {
        integrateAxis(puck, true, puck.vx, subframes);
        integrateAxis(puck, false, puck.vy, subframes);
    }

    public static int clampSpeed(int v, int max) {
        if (v > max) {
            return max;
        }
        if (v < -max) {
            return -max;
        }
        return v;
    }

    public static int applyFriction(int component, int friction) {
        if (component > 0) {
            return component - Math.min(component, friction);
        }
        if (component < 0) {
            return component + Math.min(-component, friction);
        }
        return 0;
    }
}
