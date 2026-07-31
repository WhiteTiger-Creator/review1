'use strict';

// Applies your chooseChampion() to the practice rounds in /app/cases.json and prints the index it
// returns for each. Only a convenience runner; the judging uses rounds you have not seen.
const fs = require('fs');
const path = require('path');
const { chooseChampion } = require('./strategy.js');

const rounds = JSON.parse(fs.readFileSync(path.join(__dirname, 'cases.json'), 'utf8')).rounds;
for (const r of rounds) {
  let out;
  try {
    out = chooseChampion({ mine: r.mine.map((u) => ({ ...u })), rivals: r.rivals.map((u) => ({ ...u })) });
  } catch (e) {
    out = 'ERROR: ' + e.message;
  }
  console.log(r.name + ': ' + JSON.stringify(out));
}
