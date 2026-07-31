import { resolve_apex } from "../apex/apex_phase";
import { clashDamage } from "./clash_math";
import { VaultRuntime } from "./types";
import { spendTurn, printState, finalize } from "./cmd_probe";
import { maybeDescend } from "./floor_gate";

function foeKey(floor: number, x: number, y: number): string {
  return `${floor}:${x},${y}`;
}

export function handleAttack(state: VaultRuntime): void {
  if (!spendTurn(state)) return;
  const fk = foeKey(state.floor, state.pos.x, state.pos.y);
  const foe = state.foes[fk];
  const cell = state.grids[state.floor][state.pos.y][state.pos.x];
  if (cell === "X") {
    const before = state.apex_stage;
    const updated = resolve_apex(state, "attack");
    Object.assign(state, updated);
    state.buff = state.pouch.buff;
    if (before !== "cleared" && state.apex_stage === "cleared") {
      console.log("STATUS apex_cleared");
    } else if (state.pouch.open_flag_epoch < 1) {
      console.log("STATUS apex_resists");
    } else {
      console.log(`STATUS apex_hit hp=${state.apex_hp}`);
    }
    printState(state);
    return;
  }
  if (!foe || foe.hp <= 0) {
    console.log("STATUS no_target");
    printState(state);
    return;
  }
  const dmg = clashDamage(state.atk, state.buff, foe.def);
  foe.hp -= dmg;
  if (foe.hp <= 0) {
    delete state.foes[fk];
    state.grids[state.floor][state.pos.y][state.pos.x] = ".";
    console.log("STATUS foe_down");
    maybeDescend(state);
  } else {
    const back = clashDamage(foe.atk, 0, state.def);
    state.hp -= back;
    console.log(`STATUS foe_hit foe_hp=${foe.hp} you_hp=${state.hp}`);
    if (state.hp <= 0) {
      console.log("STATUS defeated");
      finalize(state);
      return;
    }
  }
  printState(state);
}

export function handleExit(state: VaultRuntime): void {
  if (!spendTurn(state)) return;
  finalize(state);
}
