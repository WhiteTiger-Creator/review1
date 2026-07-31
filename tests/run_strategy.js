'use strict';

// Verifier-owned runner. Loads the agent's strategy.js, applies chooseChampion() to each held-out
// round, and writes { "picks": { "<round name>": <index>|null } }. Kept apart from the scoring
// logic so the submitted code never sees the expected outcomes.
//     node run_strategy.js <appDir> <roundsPath> <outPath>
const fs = require('fs');
const path = require('path');

const [appDir, roundsPath, outPath] = process.argv.slice(2);
const { chooseChampion } = require(path.join(appDir, 'strategy.js'));
const rounds = JSON.parse(fs.readFileSync(roundsPath, 'utf8')).rounds;

const picks = {};
for (const r of rounds) {
  let out = null;
  try {
    const v = chooseChampion({ mine: r.mine.map((u) => ({ ...u })), rivals: r.rivals.map((u) => ({ ...u })) });
    if (typeof v === 'number') out = v;
  } catch (e) {
    out = null;
  }
  picks[r.name] = out;
}
fs.writeFileSync(outPath, JSON.stringify({ picks }));
process.stdout.write('chose champions for ' + rounds.length + ' rounds\n');
