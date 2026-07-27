package glideclash.api;

public enum InputStatus {
    STORED, REVISED, IDEMPOTENT, STALE_SEQUENCE,
    TOO_OLD, CONFLICT, UNKNOWN_PLAYER, INVALID_INPUT
}
