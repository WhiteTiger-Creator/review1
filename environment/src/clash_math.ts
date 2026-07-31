export function clashDamage(atk: number, buff: number, def: number): number {
  // Public formula: damage = max(1, (atk * 3 + buff) / (1 + def)) with floor division.
  const raw = Math.floor((atk * 3 + buff) / (1 + def));
  return Math.max(1, raw);
}
