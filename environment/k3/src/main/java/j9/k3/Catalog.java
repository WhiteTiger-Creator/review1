package j9.k3;

public final class Catalog {
  private Catalog() {}

  public static byte[] padded(byte[] core, int pad) {
    if (core == null) {
      core = new byte[0];
    }
    byte[] out = new byte[core.length + Math.max(0, pad)];
    System.arraycopy(core, 0, out, 0, core.length);
    for (int i = core.length; i < out.length; i++) {
      out[i] = (byte) (i & 0xff);
    }
    return out;
  }
}
