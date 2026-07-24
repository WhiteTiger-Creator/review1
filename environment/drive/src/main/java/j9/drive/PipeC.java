package j9.drive;

import j9.k2.Quad;
import j9.k3.Vial;

public final class PipeC {
  private PipeC() {}

  public static byte[] run(Quad.ProjOut proj, Vial.LedgerView view, int lim) {
    return Vial.clf_p9(proj, view, lim);
  }
}
