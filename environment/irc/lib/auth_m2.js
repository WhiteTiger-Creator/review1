export function tipEvent(journal) {
  if (!journal.length) return null;
  return journal[journal.length - 1];
}

export function lastComplete(journal) {
  for (let i = journal.length - 1; i >= 0; i--) {
    if (journal[i].complete) return journal[i];
  }
  return null;
}

export function reconcileActive(st) {
  return st.registry.active;
}

export function nextSeq(journal) {
  if (!journal.length) return 1;
  return Math.max(...journal.map((e) => e.seq)) + 1;
}
