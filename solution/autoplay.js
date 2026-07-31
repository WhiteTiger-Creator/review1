#!/usr/bin/env node
const { spawn } = require("child_process");

function parseArgs(argv) {
  let seed = "nominal";
  let out = "/app/output/vault_state.json";
  let engine = "/app/environment/dist/src/main.js";
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--seed" && argv[i + 1]) seed = argv[++i];
    else if (argv[i] === "--out" && argv[i + 1]) out = argv[++i];
    else if (argv[i] === "--engine" && argv[i + 1]) engine = argv[++i];
  }
  return { seed, out, engine };
}

function parseState(line) {
  if (!line.includes("pos=") || !line.includes("floor=")) return null;
  const num = (re, d = 0) => {
    const m = line.match(re);
    return m ? Number(m[1]) : d;
  };
  const str = (re, d = "") => {
    const m = line.match(re);
    return m ? m[1] : d;
  };
  const pm = line.match(/pos=(\d+),(\d+)/);
  const pouch = str(/pouch=\[([^\]]*)\]/);
  const used = str(/used=\[([^\]]*)\]/);
  const adj = {};
  for (const m of line.matchAll(/\b([nsew]):([^\s]+)/g)) adj[m[1]] = m[2];
  return {
    floorIdx: num(/floor=(\d+)/) - 1,
    x: pm ? Number(pm[1]) : 0,
    y: pm ? Number(pm[2]) : 0,
    pouch: pouch ? pouch.split(",").filter(Boolean) : [],
    used: used ? used.split(",").filter(Boolean) : [],
    open: num(/open_flag_epoch=(\d+)/),
    apex: str(/apex_stage=(\w+)/),
    here: str(/here=([^\s]+)/),
    turns: num(/turns_used=(\d+)/),
    adj,
  };
}

const DIRS = {
  n: [0, -1],
  s: [0, 1],
  e: [1, 0],
  w: [-1, 0],
};

function key(x, y) {
  return `${x},${y}`;
}

function updateMap(mem, st) {
  mem.grid[key(st.x, st.y)] = st.here;
  for (const [d, code] of Object.entries(st.adj)) {
    const [dx, dy] = DIRS[d];
    mem.grid[key(st.x + dx, st.y + dy)] = code;
  }
}

function floorHas(mem, codes) {
  for (const code of Object.values(mem.grid)) {
    if (codes.includes(code)) return true;
  }
  return false;
}

function collectedCount(st) {
  return st.pouch.length + st.used.length;
}

function nextUse(st) {
  for (const id of ["ember_core", "veil_latch", "crest_key"]) {
    if (!st.pouch.includes(id) || st.used.includes(id)) continue;
    if (id === "ember_core") return id;
    if (id === "veil_latch" && st.used.includes("ember_core")) return id;
    if (id === "crest_key" && st.used.includes("veil_latch")) return id;
  }
  return null;
}

/**
 * Stairs need floor loot already taken (one shard per floor 0-2) and no living
 * ward still visible on the mapped floor. Fog alone must not unlock stairs.
 */
function wantStairs(st, mem) {
  if (st.floorIdx <= 2) {
    if (collectedCount(st) < st.floorIdx + 1) return false;
    if (floorHas(mem, ["1", "2", "3"])) return false;
    if (floorHas(mem, ["E"])) return false;
  } else if (st.floorIdx === 3) {
    if (floorHas(mem, ["E"])) return false;
  }
  return true;
}

function bfs(mem, st, mode) {
  // mode: "shard" | "ward" | "stair" | "apex" | "explore"
  const start = key(st.x, st.y);
  const q = [[st.x, st.y, []]];
  const seen = new Set([start]);
  let explore = null;
  while (q.length) {
    const [x, y, path] = q.shift();
    const code = mem.grid[key(x, y)];
    if (path.length) {
      if (mode === "shard" && (code === "1" || code === "2" || code === "3")) return path;
      if (mode === "ward" && code === "E") return path;
      if (mode === "stair" && code === ">" && wantStairs(st, mem)) return path;
      if (mode === "apex" && code === "X" && st.open >= 1) return path;
    }
    for (const [d, [dx, dy]] of Object.entries(DIRS)) {
      const nx = x + dx;
      const ny = y + dy;
      const nk = key(nx, ny);
      if (seen.has(nk)) continue;
      const nc = mem.grid[nk];
      if (nc === undefined) {
        if (!explore) explore = path.concat([d]);
        continue;
      }
      if (nc === "#") continue;
      if (nc === ">" && !wantStairs(st, mem) && mode !== "explore") continue;
      if (nc === "E" && mode !== "ward" && mode !== "explore") continue;
      seen.add(nk);
      q.push([nx, ny, path.concat([d])]);
    }
  }
  if (mode === "explore") return explore;
  return explore;
}

function choose(st, mem) {
  updateMap(mem, st);

  if (st.apex === "cleared") return "exit";
  if (st.here === "1" || st.here === "2" || st.here === "3") return "take";
  if (st.here === "E") return "attack";
  const useId = nextUse(st);
  if (useId) return `use ${useId}`;
  if (st.here === "X" && st.open >= 1) return "attack";

  // Leave sealed stairs instead of oscillating on them.
  if (st.here === ">" && !wantStairs(st, mem)) {
    for (const [d, code] of Object.entries(st.adj)) {
      if (code !== "#" && code !== ">") return `move ${d}`;
    }
  }

  const needLoot = st.floorIdx <= 2 && collectedCount(st) < st.floorIdx + 1;
  const modes = needLoot
    ? ["shard", "ward", "explore", "stair"]
    : ["ward", "shard", "stair", "apex", "explore"];

  for (const mode of modes) {
    const path = bfs(mem, st, mode);
    if (path && path.length) return `move ${path[0]}`;
  }

  for (const [d, code] of Object.entries(st.adj)) {
    if (code === "#") continue;
    if (code === ">" && !wantStairs(st, mem)) continue;
    if (code === "E") continue;
    return `move ${d}`;
  }
  for (const [d, code] of Object.entries(st.adj)) {
    if (code === "E") return `move ${d}`;
  }
  return "look";
}

function play(seed, out, engine) {
  return new Promise((resolve, reject) => {
    const fs = require("fs");
    const tracePath = `/app/output/trace_${seed}.txt`;
    fs.mkdirSync("/app/output", { recursive: true });
    fs.writeFileSync(tracePath, "");
    const child = spawn("node", [engine, "--seed", seed, "--out", out], {
      stdio: ["pipe", "pipe", "inherit"],
    });
    let buf = "";
    let moves = 0;
    let mem = { grid: {}, floor: -1 };
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("autoplay timeout"));
    }, 120000);

    const send = (cmd) => {
      child.stdin.write(cmd + "\n");
      moves += 1;
      fs.appendFileSync(tracePath, cmd + "\n");
    };

    child.stdout.on("data", (chunk) => {
      buf += chunk.toString("utf8");
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("STATUS wrote")) {
          clearTimeout(timer);
          try {
            child.stdin.end();
          } catch (_) {}
          resolve({ moves, out });
          return;
        }
        const st = parseState(line);
        if (!st) continue;
        if (st.floorIdx !== mem.floor) {
          mem = { grid: {}, floor: st.floorIdx };
        }
        if (moves > 215) {
          send("exit");
          continue;
        }
        send(choose(st, mem));
      }
    });
    child.on("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
    child.on("close", () => {
      clearTimeout(timer);
      resolve({ moves, out });
    });
  });
}

async function main() {
  const { seed, out, engine } = parseArgs(process.argv);
  const result = await play(seed, out, engine);
  console.error(JSON.stringify({ ok: true, seed, ...result }));
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
