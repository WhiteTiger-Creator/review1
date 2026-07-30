import path from "path";
import { saveJson } from "./io_k1.js";

export function bindFeature(root, featureEpoch, boundGeneration, valid) {
  const stPath = path.join(root, "state", "feature_bind.json");
  const obj = {
    feature_epoch: featureEpoch,
    bound_generation: boundGeneration,
    valid: Boolean(valid),
  };
  saveJson(stPath, obj);
  return obj;
}

export function writeMaterialization(root, epoch, generation, fresh) {
  const stPath = path.join(root, "state", "materialized.json");
  const obj = { epoch, generation, fresh: Boolean(fresh) };
  saveJson(stPath, obj);
  return obj;
}
