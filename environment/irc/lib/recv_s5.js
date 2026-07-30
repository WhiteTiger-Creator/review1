import path from "path";
import { loadState, saveJson, writeJournal } from "./io_k1.js";
import { tipEvent } from "./auth_m2.js";
import { rebuildRouter } from "./route_t7.js";
import { bindFeature } from "./feat_f9.js";

export function recoverState(root) {
  const st = loadState(root);
  const tip = tipEvent(st.journal);
  if (tip && tip.complete) {
    st.registry.active = tip.ckpt;
  }
  rebuildRouter(root, st);
  bindFeature(root, st.feature.feature_epoch, st.feature.bound_generation, st.feature.valid);
  saveJson(path.join(st.state, "registry.json"), st.registry);
  writeJournal(path.join(st.state, "journal.ndjson"), st.journal);
}
