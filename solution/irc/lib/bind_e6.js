import crypto from "crypto";
import { loadState } from "./io_k1.js";
import { lastComplete } from "./auth_m2.js";

function canonicalRouter(router) {
  return JSON.stringify({
    generation: router.generation,
    checkpoint_id: router.checkpoint_id,
    routes: router.routes,
  });
}

function lineageProof(tip, featureEpoch, routerDigest, mat) {
  const fresh = mat.fresh ? "true" : "false";
  const payload = `${tip.seq}|${tip.ckpt}|${tip.generation}|${featureEpoch}|${routerDigest}|${mat.epoch}|${fresh}`;
  return crypto.createHash("sha256").update(payload).digest("hex").slice(0, 16);
}

export function buildEvalBinding(root) {
  const st = loadState(root);
  const tip = lastComplete(st.journal);
  const digest = crypto
    .createHash("sha256")
    .update(canonicalRouter(st.router))
    .digest("hex")
    .slice(0, 16);

  const mat = st.materialization;
  const policy = st.policy;
  const featureOk = Boolean(st.feature.valid);
  const freshOk = !policy.require_fresh_materialization || Boolean(mat.fresh);
  const epochOk = st.feature.feature_epoch >= policy.min_feature_epoch;
  const compatible = featureOk && freshOk && epochOk;

  if (!tip) {
    return {
      generation: 0,
      checkpoint_id: st.registry.active,
      feature_epoch: st.feature.feature_epoch,
      router_digest: digest,
      journal_tip_seq: 0,
      compatible: false,
      lineage_proof: "0".repeat(16),
    };
  }

  return {
    generation: tip.generation,
    checkpoint_id: tip.ckpt,
    feature_epoch: st.feature.feature_epoch,
    router_digest: digest,
    journal_tip_seq: tip.seq,
    compatible,
    lineage_proof: lineageProof(tip, st.feature.feature_epoch, digest, mat),
  };
}

export { canonicalRouter };
