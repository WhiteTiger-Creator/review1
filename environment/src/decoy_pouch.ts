import { Pouch } from "./types";

/** Cosmetic pouch sort decoy; never raises open_flag_epoch. */
export function sortPouchLabels(pouch: Pouch): string[] {
  return [...pouch.shards].sort();
}
