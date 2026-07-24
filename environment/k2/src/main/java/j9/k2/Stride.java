package j9.k2;

public final class Stride {
  private int flops;

  public void tick() {
    flops++;
  }

  public int getFlops() {
    return flops;
  }
}
