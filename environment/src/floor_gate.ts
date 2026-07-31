import { VaultRuntime } from "./types";
import { loadSeed } from "./seed_deck";

export function floorLabel(floorIndex: number): string {
  return `floor=${floorIndex + 1}`;
}

export function livingWardOnFloor(state: VaultRuntime, floor: number): boolean {
  const prefix = `${floor}:`;
  for (const [key, foe] of Object.entries(state.foes)) {
    if (key.startsWith(prefix) && foe.hp > 0) return true;
  }
  return false;
}

export function floorLootTaken(state: VaultRuntime, floor: number): boolean {
  const need = state.floor_loot[floor];
  if (!need) return true;
  return state.pouch.shards.includes(need) || state.pouch.used.includes(need);
}

/** Stairs only open after the floor ward is down and floor loot (if any) is taken. */
export function stairSealReason(state: VaultRuntime, cellCode: string): string | null {
  if (cellCode !== ">") return "not_stairs";
  if (livingWardOnFloor(state, state.floor)) return "need_ward_clear";
  if (state.floor <= 2 && !floorLootTaken(state, state.floor)) return "need_floor_shard";
  return null;
}

export function maybeDescend(state: VaultRuntime): boolean {
  const cell = state.grids[state.floor][state.pos.y][state.pos.x];
  if (cell !== ">") return false;
  if (stairSealReason(state, cell)) return false;
  if (state.floor >= state.grids.length - 1) return false;
  state.floors_cleared = Math.max(state.floors_cleared, state.floor + 1);
  state.floor += 1;
  const loadedStart = loadSeed(state.seed).starts[state.floor];
  state.pos = { ...loadedStart };
  console.log("STATUS descended");
  return true;
}
