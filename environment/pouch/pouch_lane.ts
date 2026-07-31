import { Pouch } from "../src/types";
import { SHARD_TEXT } from "../src/shard_catalog";

export type ApplyResult = {
  pouch: Pouch;
  outcome: "used" | "raised" | "spent_failed" | "noop";
};

export function describeShard(shardId: string): string {
  return SHARD_TEXT[shardId] || "Unknown shard.";
}

export function apply_shard(pouch: Pouch, shardId: string): ApplyResult {
  const next: Pouch = {
    shards: [...pouch.shards],
    used: [...pouch.used],
    open_flag_epoch: pouch.open_flag_epoch,
    buff: pouch.buff,
  };
  if (!next.shards.includes(shardId) || next.used.includes(shardId)) {
    return { pouch: next, outcome: "noop" };
  }

  const spendFailed = (): ApplyResult => {
    next.shards = next.shards.filter((id) => id !== shardId);
    return { pouch: next, outcome: "spent_failed" };
  };

  if (shardId === "ember_core") {
    next.shards = next.shards.filter((id) => id !== shardId);
    next.used.push(shardId);
    next.buff += 1;
    return { pouch: next, outcome: "used" };
  }
  if (shardId === "veil_latch") {
    if (!next.used.includes("ember_core")) return spendFailed();
    next.shards = next.shards.filter((id) => id !== shardId);
    next.used.push(shardId);
    next.buff += 1;
    return { pouch: next, outcome: "used" };
  }
  if (shardId === "crest_key") {
    if (!next.used.includes("veil_latch")) return spendFailed();
    next.shards = next.shards.filter((id) => id !== shardId);
    next.used.push(shardId);
    next.open_flag_epoch += 1;
    next.buff += 2;
    return { pouch: next, outcome: "raised" };
  }
  return { pouch: next, outcome: "noop" };
}

export function takeShard(pouch: Pouch, shardId: string): Pouch {
  if (pouch.shards.includes(shardId)) return pouch;
  return {
    ...pouch,
    shards: [...pouch.shards, shardId],
  };
}
