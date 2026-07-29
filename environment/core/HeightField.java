package terrain;

public final class HeightField {
    private HeightField() {}

    public static double value(int x, int y) {
        int band = (x * 13 + y * 7 + (x / 16) * 5) % 29;
        return 0.25 + band * 0.01;
    }
}
