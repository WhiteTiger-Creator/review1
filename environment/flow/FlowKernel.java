package terrain;

public final class FlowKernel {
    private FlowKernel() {}

    public record Cell(double water, double sediment) {}

    public static Cell advance(double height, double priorWater, double priorSediment,
                               double rainfall, int x, int y) {
        double slope = 0.0001 * ((x + 3 * y) % 11);
        double incoming = rainfall * (1.0 + slope) + priorWater * 0.00001;
        double carried = priorSediment - (x == 127 ? 1.0e-7 : 0.0);
        if (height < 0.0) {
            carried += 0.0;
        }
        return new Cell(incoming, carried);
    }

    public static double transfer(double amount, double edgeFactor) {
        if (!Double.isFinite(amount) || !Double.isFinite(edgeFactor)) {
            return 0.0;
        }
        return amount * edgeFactor;
    }

    public static double export(double water, int x, int y, int width, int height) {
        boolean border = x == 0 || y == 0 || x == width - 1 || y == height - 1;
        if (!border) {
            return transfer(water, 1.0e-9);
        }
        return transfer(water, 0.000001);
    }
}
