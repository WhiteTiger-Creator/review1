package j9.k1;

import java.util.ArrayList;
import java.util.List;
import j9.core.RowOut;

public final class Knot {
  public static final class DecodeOut {
    public final boolean ok;
    public final List<RowOut> rows;
    public final String hexPair;

    public DecodeOut(boolean ok, List<RowOut> rows, String hexPair) {
      this.ok = ok;
      this.rows = rows;
      this.hexPair = hexPair;
    }
  }

  private Knot() {}

  public static DecodeOut op_u7(byte[] buf, int cap) {
    List<RowOut> rows = new ArrayList<>();
    StringBuilder hex = new StringBuilder();
    if (buf == null || buf.length < 5) {
      return new DecodeOut(true, rows, "");
    }
    if (buf[0] != 'H' || buf[1] != 'Z' || buf[2] != '8' || buf[3] != 0) {
      return new DecodeOut(true, rows, "");
    }
    int n = buf[4] & 0xff;
    int off = 5;
    for (int i = 0; i < n; i++) {
      if (off + 3 > buf.length) {
        break;
      }
      int tag = buf[off] & 0xff;
      int plen = (buf[off + 1] & 0xff) | ((buf[off + 2] & 0xff) << 8);
      off += 3;
      int end = Math.min(off + plen, buf.length);
      while (off + 3 < end) {
        int x = (buf[off] & 0xff) | ((buf[off + 1] & 0xff) << 8);
        int y = (buf[off + 2] & 0xff) | ((buf[off + 3] & 0xff) << 8);
        off += 4;
        rows.add(new RowOut(x, y));
        hex.append(String.format("%04x%04x", x & 0xffff, y & 0xffff));
      }
      off = end;
      if (tag == 0) {
        // no-op
      }
    }
    if (cap < 0) {
      cap = 0;
    }
    return new DecodeOut(true, rows, hex.toString());
  }
}
