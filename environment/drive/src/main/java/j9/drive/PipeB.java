package j9.drive;

import java.util.List;
import j9.core.RowOut;
import j9.k2.Quad;

public final class PipeB {
  private PipeB() {}

  public static Quad.ProjOut run(Quad.TabState state, List<RowOut> slice) {
    return Quad.tab_m4(state, slice);
  }
}
