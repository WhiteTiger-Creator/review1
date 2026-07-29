package terrain;

public final class SedimentLedger {
    private double sediment;
    private double tileScratch;
    private int commits;

    public SedimentLedger(double initial) {
        this.sediment = initial;
        this.tileScratch = 0.0;
        this.commits = 0;
    }

    public double value() {
        return sediment;
    }

    public void observeCell(double carried) {
        tileScratch += carried - sediment;
        sediment = carried;
    }

    public void commitTile() {
        sediment += tileScratch;
        tileScratch = 0.0;
        commits += 1;
    }

    public int commitCount() {
        return commits;
    }
}
