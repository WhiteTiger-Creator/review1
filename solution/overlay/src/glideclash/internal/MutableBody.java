package glideclash.internal;

public final class MutableBody {
    public final String id;
    public final boolean puck;
    public final int radius;
    public final int speed;
    public final int player;
    public final int homeMinX;
    public final int homeMaxX;
    public final int homeMinY;
    public final int homeMaxY;
    public int x;
    public int y;
    public int vx;
    public int vy;
    public int xRemainder;
    public int yRemainder;
    public boolean active;

    public MutableBody(
        String id, boolean puck, int radius, int speed, int player,
        int homeMinX, int homeMaxX, int homeMinY, int homeMaxY,
        int x, int y, int vx, int vy, int xRemainder, int yRemainder, boolean active
    ) {
        this.id = id;
        this.puck = puck;
        this.radius = radius;
        this.speed = speed;
        this.player = player;
        this.homeMinX = homeMinX;
        this.homeMaxX = homeMaxX;
        this.homeMinY = homeMinY;
        this.homeMaxY = homeMaxY;
        this.x = x;
        this.y = y;
        this.vx = vx;
        this.vy = vy;
        this.xRemainder = xRemainder;
        this.yRemainder = yRemainder;
        this.active = active;
    }

    public MutableBody copy() {
        return new MutableBody(
            id, puck, radius, speed, player,
            homeMinX, homeMaxX, homeMinY, homeMaxY,
            x, y, vx, vy, xRemainder, yRemainder, active
        );
    }

    public void setFrom(MutableBody o) {
        x = o.x;
        y = o.y;
        vx = o.vx;
        vy = o.vy;
        xRemainder = o.xRemainder;
        yRemainder = o.yRemainder;
        active = o.active;
    }
}
