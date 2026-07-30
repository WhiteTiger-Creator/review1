# Tile traversal notes

Skirmish map tiles are 16 columns by 8 rows. The 128 by 96 battlefield therefore
contains 96 complete tiles in 8 columns and 12 rows. Border cells remain part of
their tile and contribute to the same totals as interior cells. A tile may retain
local state while it is being processed, but residents from a finished tile must
be released before the next tile begins so the reported peak stays at one tile.
The report still describes the complete logical map.
