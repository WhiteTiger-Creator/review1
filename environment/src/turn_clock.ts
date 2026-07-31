import { TURN_BUDGET } from "./types";

export function withinBudget(turns: number): boolean {
  return turns <= TURN_BUDGET;
}

export function tick(turns: number): number {
  return turns + 1;
}
