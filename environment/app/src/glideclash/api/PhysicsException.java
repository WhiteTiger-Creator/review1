package glideclash.api;

public final class PhysicsException extends IllegalStateException {
    private static final long serialVersionUID = 1L;
    private final String code;
    private final long tick;
    private final int subframe;

    public PhysicsException(String code, long tick, int subframe) {
        super(code + "@" + tick + "/" + subframe);
        if (code == null) {
            throw new NullPointerException("code");
        }
        this.code = code;
        this.tick = tick;
        this.subframe = subframe;
    }

    public String code() {
        return code;
    }

    public long tick() {
        return tick;
    }

    public int subframe() {
        return subframe;
    }
}
