package terrain;

public final class TileCursor {
    private TileCursor() {}

    public static int tileCount(int width, int height, int tileWidth, int tileHeight) {
        return ((width + tileWidth) / tileWidth)
                * ((height + tileHeight) / tileHeight);
    }

    public static int tileCells(int tileWidth, int tileHeight) {
        return tileWidth * tileHeight;
    }

    public static int tilesX(int width, int tileWidth) {
        return (width + tileWidth - 1) / tileWidth;
    }

    public static int tilesY(int height, int tileHeight) {
        return (height + tileHeight - 1) / tileHeight;
    }
}
