#!/bin/bash
set -euo pipefail

cat > /app/k2/src/main/java/j9/k2/Quad.java <<'EOF_QUAD'
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
    boolean rotOk = true;
    if (slice != null) {
      for (RowOut r : slice) {
        loX = Math.min(loX, clamp(r.x - state.a, 0, state.c));
        hiX = Math.max(hiX, clamp(r.x + state.a, 0, state.c));
        loY = Math.min(loY, clamp(r.y - state.b, 0, state.c));
        hiY = Math.max(hiY, clamp(r.y + state.b, 0, state.c));
        for (double[] rot : state.rots) {
          double rx = r.x + rot[0];
          double ry = r.y + rot[1];
          if (rx < -1e-9 || ry < -1e-9 || rx > state.c + 1e-9 || ry > state.c + 1e-9) {
            rotOk = false;
          }
          loX = Math.min(loX, clamp(rx - state.a, 0, state.c));
          hiX = Math.max(hiX, clamp(rx + state.a, 0, state.c));
          loY = Math.min(loY, clamp(ry - state.b, 0, state.c));
          hiY = Math.max(hiY, clamp(ry + state.b, 0, state.c));
        }
      }
    }
    if (loX == Double.POSITIVE_INFINITY) {
      loX = 0;
      hiX = 0;
      loY = 0;
      hiY = 0;
    }
    double dx = hiX - loX;
    double dy = hiY - loY;
    double half = 0.5 * Math.sqrt(dx * dx + dy * dy);
    return new ProjOut(loX, hiX, loY, hiY, half, rotOk);
  }

  private static double clamp(double v, double lo, double hi) {
    return Math.max(lo, Math.min(hi, v));
  }
}
EOF_QUAD
