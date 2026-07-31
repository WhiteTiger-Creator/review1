/** Cosmetic apex meter unused by the live apex handler. */
export function apexMeter(hp: number, maxHp: number): number {
  if (maxHp <= 0) return 0;
  return Math.floor((100 * hp) / maxHp);
}
