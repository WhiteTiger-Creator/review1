const { spawn } = require("child_process");

function parseArgs(argv) {
  throw new Error("nav_core stub: parseArgs unset");
}

function parseState(line) {
  throw new Error("nav_core stub: parseState unset");
}

function key(x, y) {
  throw new Error("nav_core stub: key unset");
}

function updateMap(mem, st) {
  throw new Error("nav_core stub: updateMap unset");
}

function missingShards(st) {
  throw new Error("nav_core stub: missingShards unset");
}

function nextUse(st) {
  throw new Error("nav_core stub: nextUse unset");
}

function wantStairs(st) {
  throw new Error("nav_core stub: wantStairs unset");
}

function goalFilter(st, code, walkFoes) {
  throw new Error("nav_core stub: goalFilter unset");
}

function bfs(mem, st, preferFoes) {
  throw new Error("nav_core stub: bfs unset");
}

const DIRS = { n: [0, -1], s: [0, 1], e: [1, 0], w: [-1, 0] };
module.exports = { parseArgs, parseState, key, updateMap, missingShards, nextUse, wantStairs, goalFilter, bfs, DIRS };
