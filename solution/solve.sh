#!/bin/bash
set -euo pipefail

# Reconstruct the Dropforge engine: connected-group gravity with cascades,
# and the house payout - a stepped row table, a doubling cascade multiplier,
# a level that climbs with the rows cleared so far, and a bonus for emptying
# the well. All of it recovered from the recorded games.

cat > /app/engine.js <<'JS'
'use strict';

// Dropforge replay engine: script -> final well + score.
//
// House conventions recovered from the recorded games:
//  - Sticky gravity: after a clear, each 4-connected group of filled cells
//    falls independently until it rests, and rows completed by the settling
//    clear again as a cascade. This loop takes the bottom-most group first,
//    but the recordings play out the same whatever order it picks.
//  - Row table: 1/2/3/4 rows at once are worth 10/30/50/80 before any
//    multiplier.
//  - Cascade: step c of a chain doubles, so it pays its base times
//    2^(c-1). The chain count restarts with each piece.
//  - Level: every 5 rows cleared over the game lifts the level by one. The
//    level is read once at the start of each piece, from the rows cleared
//    before it, and a clear pays its points times that level.
//  - Perfect clear: a piece that leaves the well completely empty pays 200.
//  - Overflow: cells resting above the top edge are discarded and play
//    continues with the rest of the piece.
//  - Wall rotation: a rotation overlapping the right wall is kicked inward.

const fs = require('fs');

const WIDTH = 9;
const HEIGHT = 16;

const SHAPES = {
  I: [[[0, 0], [0, 1], [0, 2], [0, 3]],
      [[0, 0], [1, 0], [2, 0], [3, 0]]],
  O: [[[0, 0], [0, 1], [1, 0], [1, 1]]],
  L: [[[0, 0], [1, 0], [2, 0], [2, 1]],
      [[0, 0], [0, 1], [0, 2], [1, 0]],
      [[0, 0], [0, 1], [1, 1], [2, 1]],
      [[1, 0], [1, 1], [1, 2], [0, 2]]],
  S: [[[0, 1], [0, 2], [1, 0], [1, 1]],
      [[0, 0], [1, 0], [1, 1], [2, 1]]],
  T: [[[0, 0], [0, 1], [0, 2], [1, 1]],
      [[0, 1], [1, 0], [1, 1], [2, 1]],
      [[1, 0], [1, 1], [1, 2], [0, 1]],
      [[0, 0], [1, 0], [2, 0], [1, 1]]],
};

const BASE_SCORE = { 1: 10, 2: 30, 3: 50, 4: 80 };
const LEVEL_STEP = 5;
const PERFECT_BONUS = 200;

function makeWell() {
  return {
    grid: Array.from({ length: HEIGHT }, () => new Array(WIDTH).fill(0)),
    score: 0,
    rowsDone: 0,   // rows cleared so far, which drives the level
  };
}

function shapeCells(piece, rot, col) {
  const cells = SHAPES[piece][rot % SHAPES[piece].length];
  const w = Math.max(...cells.map(rc => rc[1])) + 1;
  if (col + w > WIDTH) col = WIDTH - w;      // wall kick inward
  return [cells, col];
}

function collides(well, cells, top, col) {
  for (const [r, c] of cells) {
    const rr = top + r;
    if (rr >= HEIGHT) return true;
    if (rr >= 0 && well.grid[rr][col + c] !== 0) return true;
  }
  return false;
}

function fullRows(well) {
  const out = [];
  for (let i = 0; i < HEIGHT; i++) {
    if (well.grid[i].every(v => v !== 0)) out.push(i);
  }
  return out;
}

function components(well) {
  const seen = Array.from({ length: HEIGHT }, () => new Array(WIDTH).fill(false));
  const comps = [];
  for (let r = 0; r < HEIGHT; r++) {
    for (let c = 0; c < WIDTH; c++) {
      if (well.grid[r][c] !== 0 && !seen[r][c]) {
        const stack = [[r, c]];
        const comp = [];
        seen[r][c] = true;
        while (stack.length) {
          const [rr, cc] = stack.pop();
          comp.push([rr, cc]);
          for (const [dr, dc] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
            const nr = rr + dr, nc = cc + dc;
            if (nr >= 0 && nr < HEIGHT && nc >= 0 && nc < WIDTH &&
                well.grid[nr][nc] !== 0 && !seen[nr][nc]) {
              seen[nr][nc] = true;
              stack.push([nr, nc]);
            }
          }
        }
        comps.push(comp);
      }
    }
  }
  return comps;
}

function dropDistance(well, comp) {
  const inComp = new Set(comp.map(([r, c]) => r * WIDTH + c));
  let d = 0;
  for (;;) {
    const nd = d + 1;
    let ok = true;
    for (const [r, c] of comp) {
      const nr = r + nd;
      if (nr >= HEIGHT) { ok = false; break; }
      if (!inComp.has(nr * WIDTH + c) && well.grid[nr][c] !== 0) {
        ok = false;
        break;
      }
    }
    if (!ok) return d;
    d = nd;
  }
}

function settle(well) {
  for (;;) {
    const comps = components(well);
    comps.sort((a, b) => {
      const maxA = Math.max(...a.map(rc => rc[0]));
      const maxB = Math.max(...b.map(rc => rc[0]));
      if (maxA !== maxB) return maxB - maxA;
      return Math.min(...a.map(rc => rc[1])) - Math.min(...b.map(rc => rc[1]));
    });
    let moved = false;
    for (const comp of comps) {
      const d = dropDistance(well, comp);
      if (d > 0) {
        const vals = comp.map(([r, c]) => well.grid[r][c]);
        for (const [r, c] of comp) well.grid[r][c] = 0;
        comp.forEach(([r, c], i) => { well.grid[r + d][c] = vals[i]; });
        moved = true;
        break;
      }
    }
    if (!moved) return;
  }
}

function resolveClears(well, level) {
  let chain = 0;
  for (;;) {
    const rows = fullRows(well);
    if (!rows.length) break;
    chain += 1;
    const k = Math.min(rows.length, 4);
    well.score += BASE_SCORE[k] * Math.pow(2, chain - 1) * level;
    well.rowsDone += rows.length;
    for (const i of rows) well.grid[i] = new Array(WIDTH).fill(0);
    settle(well);
  }
  return chain > 0;
}

function isEmpty(well) {
  return well.grid.every(row => row.every(v => v === 0));
}

function dropPiece(well, pid, piece, rot, col) {
  const [cells, c0] = shapeCells(piece, rot, col);
  const h = Math.max(...cells.map(rc => rc[0])) + 1;
  let top = -h;
  for (;;) {
    const nxt = top + 1;
    if (collides(well, cells, nxt, c0)) break;
    top = nxt;
  }
  const placed = cells
    .map(([r, c]) => [top + r, c0 + c])
    .filter(([r]) => r >= 0);              // overflow cells are clipped
  for (const [r, c] of placed) well.grid[r][c] = pid;

  // The level is fixed for the whole piece, read from the rows cleared
  // before it; a piece that empties the well pays the perfect-clear bonus.
  const level = 1 + Math.floor(well.rowsDone / LEVEL_STEP);
  const cleared = resolveClears(well, level);
  if (cleared && isEmpty(well)) well.score += PERFECT_BONUS;
}

function main() {
  const path = process.argv[2];
  if (!path) {
    process.stderr.write('usage: node engine.js <game.json>\n');
    process.exit(2);
  }
  const game = JSON.parse(fs.readFileSync(path, 'utf8'));
  const well = makeWell();
  game.script.forEach((e, i) => dropPiece(well, i + 1, e.piece, e.rot, e.col));
  process.stdout.write(JSON.stringify({ well: well.grid, score: well.score }) + '\n');
}

main();
JS

# Smoke check: replay every shipped recording and match its final state.
node - <<'CHECK'
const fs = require('fs');
const { execFileSync } = require('child_process');
for (const f of fs.readdirSync('/app/games')) {
  const blob = JSON.parse(fs.readFileSync('/app/games/' + f, 'utf8'));
  fs.writeFileSync('/tmp/g.json', JSON.stringify({ script: blob.script }));
  const got = JSON.parse(execFileSync('node', ['/app/engine.js', '/tmp/g.json'], { encoding: 'utf8' }));
  if (JSON.stringify(got) !== JSON.stringify(blob.final)) {
    console.error('mismatch on ' + f);
    process.exit(1);
  }
}
console.log('all shipped recordings reproduced');
CHECK
