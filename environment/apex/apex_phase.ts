import { ApexAction, VaultRuntime } from "../src/types";
import { clashDamage } from "../src/clash_math";

export function resolve_apex(state: VaultRuntime, action: ApexAction): VaultRuntime {
  const next = { ...state, pouch: { ...state.pouch } };
  if (action !== "attack") {
    return next;
  }
  if (next.apex_stage === "cleared") {
    return next;
  }
  if (next.pouch.open_flag_epoch < 1) {
    next.apex_stage = "locked";
    return next;
  }
  next.apex_stage = "open";
  const dmg = clashDamage(next.atk, next.buff, 2);
  next.apex_hp = Math.max(0, next.apex_hp - dmg);
  if (next.apex_hp <= 0) {
    next.apex_stage = "cleared";
    if (next.floors_cleared < 5) {
      next.floors_cleared = 5;
    }
  }
  return next;
}
