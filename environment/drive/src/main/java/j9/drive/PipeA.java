package j9.drive;

import j9.k1.Knot;

public final class PipeA {
  private PipeA() {}

  public static Knot.DecodeOut run(byte[] buf, int cap) {
    return Knot.op_u7(buf, cap);
  }
}
