package j9.k3;

import j9.k2.Quad.ProjOut;

public final class Vial {
  public static final class LedgerView {
    public final int[] rid;
    public final double[] vPre;
    public final double[] vPost;
    public final double[] delta;
    public final String[] tag;

    public LedgerView(int[] rid, double[] vPre, double[] vPost, double[] delta, String[] tag) {
      this.rid = rid;
      this.vPre = vPre;
      this.vPost = vPost;
      this.delta = delta;
      this.tag = tag;
    }
  }

  private Vial() {}

  public static byte[] clf_p9(ProjOut proj, LedgerView view, int lim) {
    double sumPre = 0;
    double sumPost = 0;
    int n = view == null || view.vPre == null ? 0 : view.vPre.length;
    for (int i = 0; i < n; i++) {
      sumPre += view.vPre[i];
      sumPost += view.vPost[i];
    }
    int viol = 0;
    if (sumPre - sumPost < 0.05 * Math.max(1, n)) {
      viol = 1;
    }
    String mode = "sum";
    StringBuilder sb = new StringBuilder();
    sb.append("v=").append(viol).append(";mode=").append(mode);
    sb.append(";hx=").append(proj == null ? 0 : proj.hiX);
    if (lim > 0 && sb.length() > lim) {
      return sb.substring(0, lim).getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }
    return sb.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
  }
}
