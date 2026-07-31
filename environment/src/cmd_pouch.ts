import { apply_shard, takeShard, describeShard } from "../pouch/pouch_lane";
import { VaultRuntime } from "./types";
import { spendTurn, printState } from "./cmd_probe";
import { maybeDescend } from "./floor_gate";

function shardKey(floor: number, x: number, y: number): string {
  return `${floor}:${x},${y}`;
}

export function handleTake(state: VaultRuntime): void {
  if (!spendTurn(state)) return;
  const sk = shardKey(state.floor, state.pos.x, state.pos.y);
  const sid = state.shard_at[sk];
  if (!sid) {
    console.log("STATUS nothing_to_take");
    printState(state);
    return;
  }
  state.pouch = takeShard(state.pouch, sid);
  delete state.shard_at[sk];
  const ch = state.grids[state.floor][state.pos.y][state.pos.x];
  if (ch === "1" || ch === "2" || ch === "3") {
    state.grids[state.floor][state.pos.y][state.pos.x] = ".";
  }
  console.log(`STATUS took ${sid}`);
  console.log(`SHARD_TEXT id=${sid} :: ${describeShard(sid)}`);
  maybeDescend(state);
  printState(state);
}

export function handleUse(state: VaultRuntime, shardId: string): void {
  if (!spendTurn(state)) return;
  const result = apply_shard(state.pouch, shardId);
  state.pouch = result.pouch;
  state.buff = state.pouch.buff;
  if (result.outcome === "raised") {
    console.log("STATUS open_flag_raised");
  } else if (result.outcome === "used") {
    console.log(`STATUS used ${shardId}`);
  } else if (result.outcome === "spent_failed") {
    console.log(`STATUS use_spent_failed ${shardId}`);
  } else {
    console.log(`STATUS use_no_effect ${shardId}`);
  }
  maybeDescend(state);
  printState(state);
}
