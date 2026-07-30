import path from "path";
import { saveJson } from "./io_k1.js";
import { lastComplete, reconcileActive } from "./auth_m2.js";

export function rebuildRouter(root, st) {
  const active = reconcileActive(st);
  const tip = lastComplete(st.journal);
  const gen = tip ? tip.generation : 0;
  const router = {
    generation: gen,
    checkpoint_id: active,
    routes: [
      { shard: 0, target: active },
      { shard: 1, target: active },
    ],
  };
  saveJson(path.join(st.state, "router.json"), router);
  st.router = router;
  return router;
}
