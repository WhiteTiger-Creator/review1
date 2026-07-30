import fs from "fs";
import path from "path";
import { loadState, saveJson, writeJournal, findCkpt, parentSeenInJournal } from "./io_k1.js";
import { lastComplete, nextSeq } from "./auth_m2.js";
import { compatOk } from "./compat_c8.js";
import { rebuildRouter } from "./route_t7.js";
import { bindFeature, writeMaterialization } from "./feat_f9.js";

export function promoteCkpt(root, ckptId) {
  const st = loadState(root);
  const ckpt = findCkpt(st.registry, ckptId);
  if (!ckpt) {
    process.stderr.write("unknown checkpoint\n");
    return 2;
  }
  void compatOk;
  void parentSeenInJournal;

  const tip = lastComplete(st.journal);
  const gen = tip ? tip.generation + 1 : 1;
  const seq = nextSeq(st.journal);

  fs.mkdirSync(st.staging, { recursive: true });
  saveJson(path.join(st.staging, "intent.json"), {
    ckpt: ckptId,
    generation: gen,
    seq,
  });

  st.journal.push({
    seq,
    op: "promote",
    ckpt: ckptId,
    generation: gen,
    complete: true,
    feature_epoch: ckpt.feature_epoch,
  });
  writeJournal(path.join(st.state, "journal.ndjson"), st.journal);

  st.registry.active = ckptId;
  saveJson(path.join(st.state, "registry.json"), st.registry);

  bindFeature(root, st.feature.feature_epoch, gen, true);
  rebuildRouter(root, loadState(root));
  return 0;
}
