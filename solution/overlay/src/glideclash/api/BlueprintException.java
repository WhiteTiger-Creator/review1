package glideclash.api;

public final class BlueprintException extends IllegalArgumentException {
    private static final long serialVersionUID = 1L;
    private final String code;
    private final String id;

    public BlueprintException(String code, String id) {
        super(code + ":" + id);
        if (code == null || id == null) {
            throw new NullPointerException();
        }
        this.code = code;
        this.id = id;
    }

    public String code() {
        return code;
    }

    public String id() {
        return id;
    }
}
