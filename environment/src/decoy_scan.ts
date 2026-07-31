import { ProbeCtx, Cell } from "./types";

/** Unused fog overlay decoy; not consulted by the live stdin loop. */
export function fogOverlay(_ctx: ProbeCtx, _xy: Cell): string {
  return "haze";
}
