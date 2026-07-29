package terrain;

public final class TileBuffer {
    private final CellState[] slots;
    private int filled;
    private long peak;
    private long lifetime;

    public TileBuffer(int capacity) {
        this.slots = new CellState[capacity];
        this.filled = 0;
        this.peak = 0;
        this.lifetime = 0;
    }

    public void beginTile() {
        peak = Math.max(peak, filled);
        lifetime += filled;
    }

    public void put(CellState state) {
        if (filled >= slots.length) {
            throw new IllegalStateException("tile capacity exceeded");
        }
        slots[filled++] = state;
        peak = Math.max(peak, filled);
        lifetime += 1;
    }

    public void endTile() {
        peak = Math.max(peak, filled);
    }

    public long peakCells() {
        return Math.max(peak, lifetime);
    }

    public int capacity() {
        return slots.length;
    }

    public int residents() {
        return filled;
    }
}
