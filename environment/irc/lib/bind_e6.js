import crypto from "crypto";
import { loadState } from "./io_k1.js";
import { tipEvent, reconcileActive } from "./auth_m2.js";

function canonicalRouter(router) {
  return JSON.stringify({
    generation: router.generation,
    checkpoint_id: router.checkpoint_id,
    routes: router.routes,
  });
}

export function buildEvalBinding(root) {
  const st = loadState(root);
  const tip = tipEvent(st.journal);
  const active = reconcileActive(st);
  const digest = crypto
    .createHash("sha256")
    .update(canonicalRouter(st.router))
    .digest("hex")
    .slice(0, 16);
  return {
    generation: tip ? tip.generation : 0,
    checkpoint_id: active,
    feature_epoch: st.feature.feature_epoch,
    router_digest: digest,
    journal_tip_seq: tip ? tip.seq : 0,
    compatible: st.feature.valid,
    lineage_proof: "pending",
  };
}

export { canonicalRouter };
