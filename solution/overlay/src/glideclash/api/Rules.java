package glideclash.api;

public record Rules(
    int width, int height, int subframes, int rollbackWindow,
    int friction, int maxSpeed, int serveSpeed
) {}
