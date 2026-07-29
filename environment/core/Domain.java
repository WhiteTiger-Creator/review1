package terrain;

public final class Domain {
    private Domain() {}

    public static int cells(int width, int height) {
        return Math.multiplyExact(width, height);
    }
}
