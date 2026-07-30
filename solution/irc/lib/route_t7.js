import path from "path";
import { saveJson } from "./io_k1.js";
import { lastComplete } from "./auth_m2.js";

export function rebuildRouter(root, st) {
  const tip = lastComplete(st.journal);
  const ckptId = tip ? tip.ckpt : st.registry.active;
  const gen = tip ? tip.generation : 0;
  const router = {
    generation: gen,
    checkpoint_id: ckptId,
    routes: [
      { shard: 0, target: ckptId },
      { shard: 1, target: ckptId },
    ],
  };
  saveJson(path.join(st.state, "router.json"), router);
  st.router = router;
  return router;
}
