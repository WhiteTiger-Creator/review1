package j9.core;

public final class Mesh {
  private Mesh() {}

  public static int mix(int a, int b) {
    return (a * 31) ^ b;
  }
}
