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
      return new DecodeOut(false, rows, "");
    }
    if (buf[0] != 'H' || buf[1] != 'Z' || buf[2] != '8' || buf[3] != 0) {
      return new DecodeOut(false, rows, "");
    }
    int n = buf[4] & 0xff;
    int off = 5;
    for (int i = 0; i < n; i++) {
      if (off + 3 > buf.length) {
        return new DecodeOut(false, rows, hex.toString());
      }
      int tag = buf[off] & 0xff;
      int plen = (buf[off + 1] & 0xff) | ((buf[off + 2] & 0xff) << 8);
      off += 3;
      if (off + plen > buf.length || off + plen > cap) {
        return new DecodeOut(false, rows, hex.toString());
      }
      int end = off + plen;
      if ((plen & 3) != 0) {
        return new DecodeOut(false, rows, hex.toString());
      }
      while (off + 3 < end) {
        int x;
        int y;
        if (tag == 2) {
          x = ((buf[off] & 0xff) << 8) | (buf[off + 1] & 0xff);
          y = ((buf[off + 2] & 0xff) << 8) | (buf[off + 3] & 0xff);
        } else if (tag == 1) {
          x = (buf[off] & 0xff) | ((buf[off + 1] & 0xff) << 8);
          y = (buf[off + 2] & 0xff) | ((buf[off + 3] & 0xff) << 8);
        } else {
          return new DecodeOut(false, rows, hex.toString());
        }
        off += 4;
        rows.add(new RowOut(x, y));
        hex.append(String.format("%04x%04x", x & 0xffff, y & 0xffff));
      }
      off = end;
    }
    return new DecodeOut(true, rows, hex.toString());
  }
}
