/** Soft mask helper kept for parity with decoy fog; live path uses probe helpers. */
export function softMask(code: string, seen: boolean): string {
  return seen ? code : "?";
}
