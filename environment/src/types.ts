export type Cell = { x: number; y: number };

export type CellView = {
  code: string;
  walkable: boolean;
  shardId?: string;
  foe?: { name: string; hp: number; atk: number; def: number };
};

export type ProbeCtx = {
  floor: number;
  grid: string[][];
  visited: Set<string>;
};

export type Pouch = {
  shards: string[];
  used: string[];
  open_flag_epoch: number;
  buff: number;
};

export type ApexAction = "attack" | "probe";

export type VaultRuntime = {
  seed: string;
  floor: number;
  pos: Cell;
  hp: number;
  atk: number;
  def: number;
  buff: number;
  turns_used: number;
  floors_cleared: number;
  pouch: Pouch;
  apex_stage: "locked" | "open" | "cleared";
  apex_hp: number;
  grids: string[][][];
  foes: Record<string, { hp: number; atk: number; def: number; name: string }>;
  shard_at: Record<string, string>;
  /** Shard id that must be collected before descending each of floors 0-2. */
  floor_loot: Record<number, string>;
  done: boolean;
  outPath: string;
};

export const TURN_BUDGET = 220;
export const FLOOR_COUNT = 5;
export const VALID_SEEDS = ["nominal", "holdout", "mirror"] as const;
