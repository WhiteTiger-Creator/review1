package j9.k2;

import java.util.List;
import j9.core.RowOut;

public final class Quad {
  public static final class TabState {
    public final double a;
    public final double b;
    public final double c;
    public final double[][] rots;

    public TabState(double a, double b, double c, double[][] rots) {
      this.a = a;
      this.b = b;
      this.c = c;
      this.rots = rots == null ? new double[0][0] : rots;
    }
  }

  public static final class ProjOut {
    public final double loX;
    public final double hiX;
    public final double loY;
    public final double hiY;
    public final double halfDiag;
    public final boolean rotOk;

    public ProjOut(double loX, double hiX, double loY, double hiY, double halfDiag, boolean rotOk) {
      this.loX = loX;
      this.hiX = hiX;
      this.loY = loY;
      this.hiY = hiY;
      this.halfDiag = halfDiag;
      this.rotOk = rotOk;
    }
  }

  private Quad() {}

  public static ProjOut tab_m4(TabState state, List<RowOut> slice) {
    double loX = Double.POSITIVE_INFINITY;
    double hiX = Double.NEGATIVE_INFINITY;
    double loY = Double.POSITIVE_INFINITY;
    double hiY = Double.NEGATIVE_INFINITY;
    if (slice != null) {
      for (RowOut r : slice) {
        double x0 = r.x + state.a;
        double x1 = r.x - state.a;
        double y0 = r.y + state.b;
        double y1 = r.y - state.b;
        loX = Math.min(loX, Math.min(x0, x1));
        hiX = Math.max(hiX, Math.max(x0, x1));
        loY = Math.min(loY, Math.min(y0, y1));
        hiY = Math.max(hiY, Math.max(y0, y1));
      }
    }
    if (loX == Double.POSITIVE_INFINITY) {
      loX = 0;
      hiX = 0;
      loY = 0;
      hiY = 0;
    }
    loX = clamp(loX, 0, state.c);
    hiX = clamp(hiX, 0, state.c);
    loY = clamp(loY, 0, state.c);
    hiY = clamp(hiY, 0, state.c);
    double dx = hiX - loX;
    double dy = hiY - loY;
    double half = 0.5 * Math.sqrt(dx * dx + dy * dy);
    return new ProjOut(loX, hiX, loY, hiY, half, true);
  }

  private static double clamp(double v, double lo, double hi) {
    return Math.max(lo, Math.min(hi, v));
  }
}
