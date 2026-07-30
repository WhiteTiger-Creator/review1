import fs from "fs";
import path from "path";
import { loadState, saveJson, writeJournal, findCkpt } from "./io_k1.js";
import { lastComplete } from "./auth_m2.js";
import { rebuildRouter } from "./route_t7.js";
import { bindFeature, writeMaterialization } from "./feat_f9.js";

export function recoverState(root) {
  const st = loadState(root);

  const cleaned = st.journal.filter((ev) => ev.complete);
  writeJournal(path.join(st.state, "journal.ndjson"), cleaned);
  st.journal = cleaned;

  if (fs.existsSync(st.staging)) {
    fs.rmSync(st.staging, { recursive: true, force: true });
  }

  const tip = lastComplete(st.journal);
  if (tip) {
    st.registry.active = tip.ckpt;
    saveJson(path.join(st.state, "registry.json"), st.registry);
    const ckpt = findCkpt(st.registry, tip.ckpt);
    const epoch = ckpt ? ckpt.feature_epoch : tip.feature_epoch;
    bindFeature(root, epoch, tip.generation, true);
    const mat = st.materialization;
    if (mat.epoch !== epoch || mat.generation !== tip.generation) {
      writeMaterialization(root, mat.epoch, mat.generation, false);
    } else {
      writeMaterialization(root, epoch, tip.generation, true);
    }
  }
  rebuildRouter(root, loadState(root));
}
