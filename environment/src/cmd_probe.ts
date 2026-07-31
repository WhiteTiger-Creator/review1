import { scan_cell, adjacentCodes } from "../probe/grid_probe";
import { loadSeed } from "./seed_deck";
import { TURN_BUDGET, VaultRuntime, ProbeCtx } from "./types";
import { tick } from "./turn_clock";
import { floorLabel, stairSealReason, maybeDescend } from "./floor_gate";
import { writeVaultState } from "./exit_seal";
import { describeShard } from "../pouch/pouch_lane";

export function probeCtx(state: VaultRuntime): ProbeCtx {
  return {
    floor: state.floor,
    grid: state.grids[state.floor],
    visited: new Set<string>(),
  };
}

export function printState(state: VaultRuntime): void {
  const ctx = probeCtx(state);
  const here = scan_cell(ctx, state.pos);
  const adj = adjacentCodes(ctx, state.pos);
  const line = [
    floorLabel(state.floor),
    `pos=${state.pos.x},${state.pos.y}`,
    `hp=${state.hp}`,
    `atk=${state.atk}`,
    `def=${state.def}`,
    `buff=${state.buff}`,
    `pouch=[${state.pouch.shards.join(",")}]`,
    `used=[${state.pouch.used.join(",")}]`,
    `open_flag_epoch=${state.pouch.open_flag_epoch}`,
    `apex_stage=${state.apex_stage}`,
    `apex_hp=${state.apex_hp}`,
    `floors_cleared=${state.floors_cleared}`,
    `turns_used=${state.turns_used}`,
    `here=${here.code}`,
    `adj ${adj}`,
  ].join(" ");
  console.log(line);
}

export function spendTurn(state: VaultRuntime): boolean {
  state.turns_used = tick(state.turns_used);
  if (state.turns_used > TURN_BUDGET) {
    console.log("STATUS turn_budget_exhausted");
    finalize(state);
    return false;
  }
  return true;
}

export function finalize(state: VaultRuntime): void {
  state.buff = state.pouch.buff;
  writeVaultState(state.outPath, {
    seed: state.seed,
    floors_cleared: state.floors_cleared,
    open_flag_epoch: state.pouch.open_flag_epoch,
    apex_stage: state.apex_stage,
    turns_used: state.turns_used,
    used_chain: state.pouch.used.join(","),
  });
  state.done = true;
  console.log(`STATUS wrote ${state.outPath}`);
}

export function handleMove(state: VaultRuntime, dir: string): void {
  const delta: Record<string, { x: number; y: number }> = {
    n: { x: 0, y: -1 },
    s: { x: 0, y: 1 },
    e: { x: 1, y: 0 },
    w: { x: -1, y: 0 },
  };
  const d = delta[dir];
  if (!d) {
    console.log("STATUS bad_dir");
    return;
  }
  if (!spendTurn(state)) return;
  const nxt = { x: state.pos.x + d.x, y: state.pos.y + d.y };
  const ctx = probeCtx(state);
  const view = scan_cell(ctx, nxt);
  if (!view.walkable) {
    console.log("STATUS blocked");
    printState(state);
    return;
  }
  state.pos = nxt;
  const cell = state.grids[state.floor][nxt.y][nxt.x];
  if (cell === ">") {
    const reason = stairSealReason(state, cell);
    if (reason) {
      console.log(`STATUS stair_sealed ${reason}`);
    } else {
      maybeDescend(state);
    }
  }
  printState(state);
}

export function handleLook(state: VaultRuntime): void {
  if (!spendTurn(state)) return;
  const ctx = probeCtx(state);
  const here = scan_cell(ctx, state.pos);
  console.log(`LOOK here=${here.code} ${adjacentCodes(ctx, state.pos)}`);
  const sk = `${state.floor}:${state.pos.x},${state.pos.y}`;
  const sid = state.shard_at[sk];
  if (sid) {
    console.log(`SHARD_TEXT id=${sid} :: ${describeShard(sid)}`);
  }
  printState(state);
}
