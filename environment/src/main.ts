import * as readline from "readline";
import { loadSeed } from "./seed_deck";
import { TURN_BUDGET, VaultRuntime, VALID_SEEDS } from "./types";
import { printState, finalize } from "./cmd_probe";
import { handleMove, handleLook } from "./cmd_probe";
import { handleTake, handleUse } from "./cmd_pouch";
import { handleAttack, handleExit } from "./cmd_apex";

function parseArgs(argv: string[]): { seed: string; out: string } {
  let seed = "nominal";
  let out = "/app/output/vault_state.json";
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--seed" && argv[i + 1]) {
      seed = argv[++i];
    } else if (argv[i] === "--out" && argv[i + 1]) {
      out = argv[++i];
    }
  }
  return { seed, out };
}

function makeState(seed: string, outPath: string): VaultRuntime {
  const loaded = loadSeed(seed);
  const start = loaded.starts[0];
  for (let fi = 0; fi < loaded.grids.length; fi++) {
    for (let y = 0; y < loaded.grids[fi].length; y++) {
      for (let x = 0; x < loaded.grids[fi][y].length; x++) {
        if (loaded.grids[fi][y][x] === "S") {
          loaded.grids[fi][y][x] = ".";
        }
      }
    }
  }
  return {
    seed,
    floor: 0,
    pos: { ...start },
    hp: 40,
    atk: 4,
    def: 1,
    buff: 0,
    turns_used: 0,
    floors_cleared: 0,
    pouch: { shards: [], used: [], open_flag_epoch: 0, buff: 0 },
    apex_stage: "locked",
    apex_hp: 48,
    grids: loaded.grids,
    foes: loaded.foes,
    shard_at: loaded.shard_at,
    floor_loot: loaded.floor_loot,
    done: false,
    outPath,
  };
}

function dispatch(state: VaultRuntime, line: string): void {
  const raw = line.trim();
  if (!raw) return;
  const parts = raw.split(/\s+/);
  const cmd = parts[0];
  if (cmd === "move" && parts[1]) {
    handleMove(state, parts[1]);
  } else if (cmd === "look") {
    handleLook(state);
  } else if (cmd === "take") {
    handleTake(state);
  } else if (cmd === "use" && parts[1]) {
    handleUse(state, parts[1]);
  } else if (cmd === "attack") {
    handleAttack(state);
  } else if (cmd === "exit") {
    handleExit(state);
  } else {
    console.log("STATUS unknown_cmd");
    printState(state);
  }
}

async function main(): Promise<void> {
  const { seed, out } = parseArgs(process.argv);
  if (!(VALID_SEEDS as readonly string[]).includes(seed)) {
    console.error("seed must be nominal, holdout, or mirror");
    process.exit(2);
  }
  const state = makeState(seed, out);
  console.log(`BOOT seed=${seed} out=${out} budget=${TURN_BUDGET}`);
  printState(state);

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: false });
  for await (const line of rl) {
    if (state.done) break;
    dispatch(state, line);
    if (state.done) break;
  }
  if (!state.done) {
    finalize(state);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
