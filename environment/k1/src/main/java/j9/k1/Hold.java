package j9.k1;

public final class Hold {
  private final byte[] peek;

  public Hold(byte[] src) {
    this.peek = src == null ? new byte[0] : src.clone();
  }

  public int size() {
    return peek.length;
  }

  public int at(int i) {
    if (i < 0 || i >= peek.length) {
      return -1;
    }
    return peek[i] & 0xff;
  }
}
