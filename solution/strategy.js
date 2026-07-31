'use strict';

// The Warden's hidden rule for deciding a bout between two contenders.
//
//   score(u) = 2*power + guile - armour
//
//   A contender COUNTERS its opponent when its guile reaches the opponent's armour plus 3. A
//   contender that counters while its opponent does not wins the bout outright, whatever the
//   scores are. Otherwise the higher score wins, and level scores go to the higher power, then
//   the higher guile, then the lower armour, and finally to the challenger.
//
// The counter is what stops strength being a simple ranking: a nimble contender can beat one that
// out-scores it, so no single ordering of the roster explains the results.
const COUNTER_MARGIN = 3;

function score(u) {
  return 2 * u.power + u.guile - u.armour;
}

function counters(a, b) {
  return a.guile >= b.armour + COUNTER_MARGIN;
}

// Returns true when `a` beats `b`.
function beats(a, b) {
  const ca = counters(a, b);
  const cb = counters(b, a);
  if (ca && !cb) return true;
  if (cb && !ca) return false;
  const sa = score(a), sb = score(b);
  if (sa !== sb) return sa > sb;
  if (a.power !== b.power) return a.power > b.power;
  if (a.guile !== b.guile) return a.guile > b.guile;
  if (a.armour !== b.armour) return a.armour < b.armour;
  return true;
}

// How many of the rival's contenders this one beats.
function winsAgainst(mine, rivals) {
  let n = 0;
  for (const r of rivals) if (beats(mine, r)) n++;
  return n;
}

// The best number of bouts any single contender of yours can take.
function bestWins(round) {
  let best = -1;
  for (const m of round.mine) best = Math.max(best, winsAgainst(m, round.rivals));
  return best;
}

// The reference choice: the contender that takes the most bouts, earliest listed on a tie.
function chooseChampion(round) {
  let bestIdx = 0, bestWinsSoFar = -1;
  for (let i = 0; i < round.mine.length; i++) {
    const w = winsAgainst(round.mine[i], round.rivals);
    if (w > bestWinsSoFar) { bestWinsSoFar = w; bestIdx = i; }
  }
  return bestIdx;
}

module.exports = { chooseChampion };
