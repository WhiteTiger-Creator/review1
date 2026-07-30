package terrain;

public final class BoundaryFlux {
    private BoundaryFlux() {}

    public static double amount(int step, int width, int height) {
        return (step + 1) * 0.001 + (width + height) * 1.0e-9;
    }
}
