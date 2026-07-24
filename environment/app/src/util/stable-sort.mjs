/** Code-point lexicographic compare (not locale-sensitive). */
export function codePointCompare(a, b) {
  const sa = String(a);
  const sb = String(b);
  const max = Math.max(sa.length, sb.length);
  for (let i = 0; i < max; i++) {
    const ca = i < sa.length ? sa.codePointAt(i) : -1;
    const cb = i < sb.length ? sb.codePointAt(i) : -1;
    if (ca !== cb) return ca - cb;
    if (ca !== undefined && ca > 0xffff) i++;
  }
  return 0;
}

/** Code-point stable sort for set-like string arrays. */
export function stableSortStrings(values) {
  return [...values].sort(codePointCompare);
}
