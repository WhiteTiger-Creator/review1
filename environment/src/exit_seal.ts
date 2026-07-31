import * as crypto from "crypto";

export function sealDigest(
  seed: string,
  floorsCleared: number,
  apexStage: string,
  turnsUsed: number,
  usedChain: string
): string {
  const payload = `${seed}|${floorsCleared}|${apexStage}|${turnsUsed}|${usedChain}`;
  return crypto.createHash("sha256").update(payload, "utf8").digest("hex");
}

export function writeVaultState(
  outPath: string,
  fields: {
    seed: string;
    floors_cleared: number;
    open_flag_epoch: number;
    apex_stage: string;
    turns_used: number;
    used_chain: string;
  }
): void {
  const fs = require("fs") as typeof import("fs");
  const path = require("path") as typeof import("path");
  const digest = sealDigest(
    fields.seed,
    fields.floors_cleared,
    fields.apex_stage,
    fields.turns_used,
    fields.used_chain
  );
  const body = {
    seed: fields.seed,
    floors_cleared: fields.floors_cleared,
    open_flag_epoch: fields.open_flag_epoch,
    apex_stage: fields.apex_stage,
    turns_used: fields.turns_used,
    used_chain: fields.used_chain,
    exit_seal_digest: digest,
  };
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(body, null, 2) + "\n", "utf8");
}
