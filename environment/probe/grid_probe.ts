import { Cell, CellView, ProbeCtx } from "../src/types";

function key(c: Cell): string {
  return `${c.x},${c.y}`;
}

export function scan_cell(ctx: ProbeCtx, xy: Cell): CellView {
  const row = ctx.grid[xy.y];
  if (!row || xy.x < 0 || xy.x >= row.length) {
    return { code: "#", walkable: false };
  }
  const ch = row[xy.x];
  ctx.visited.add(key(xy));
  if (ch === "#") return { code: "#", walkable: false };
  if (ch === ".") return { code: ".", walkable: true };
  if (ch === ">") return { code: ">", walkable: true };
  if (ch === "@") return { code: "@", walkable: true };
  if (ch === "X") return { code: "X", walkable: true };
  if (ch === "E") return { code: "E", walkable: true };
  if (ch === "1" || ch === "2" || ch === "3") {
    return { code: ch, walkable: true };
  }
  return { code: ch, walkable: ch !== "#" };
}

export function adjacentCodes(ctx: ProbeCtx, pos: Cell): string {
  const dirs: Array<[string, Cell]> = [
    ["n", { x: pos.x, y: pos.y - 1 }],
    ["s", { x: pos.x, y: pos.y + 1 }],
    ["e", { x: pos.x + 1, y: pos.y }],
    ["w", { x: pos.x - 1, y: pos.y }],
  ];
  return dirs
    .map(([d, c]) => `${d}:${scan_cell(ctx, c).code}`)
    .join(" ");
}
