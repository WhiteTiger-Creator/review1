import path from "path";
import { loadState, saveJson, writeJournal } from "./io_k1.js";
import { nextSeq } from "./auth_m2.js";

export function rollbackGen(root, generation) {
  const st = loadState(root);
  const target = st.journal.find(
    (e) => e.complete && e.op === "promote" && e.generation === generation,
  );
  if (!target) {
    process.stderr.write("unknown generation\n");
    return 2;
  }
  const seq = nextSeq(st.journal);
  st.journal.push({
    seq,
    op: "rollback",
    ckpt: target.ckpt,
    generation: target.generation,
    complete: true,
    feature_epoch: target.feature_epoch,
  });
  writeJournal(path.join(st.state, "journal.ndjson"), st.journal);
  st.registry.active = target.ckpt;
  saveJson(path.join(st.state, "registry.json"), st.registry);
  return 0;
}
