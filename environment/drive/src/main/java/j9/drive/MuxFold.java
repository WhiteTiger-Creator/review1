package j9.drive;

public final class MuxFold {
  private MuxFold() {}

  public static int mux_fold(Runnable side, Runnable gate) {
    if (side != null) {
      side.run();
    }
    if (gate != null) {
      gate.run();
    }
    return 1;
  }
}
